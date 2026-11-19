"""Book page → word/definition pairs.

Primary: Anthropic Claude vision with structured JSON output (validated, 1 retry).
Fallback: Tesseract OCR + heuristic parser.
MOCK mode (no ANTHROPIC_API_KEY): returns sample pairs.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re

from django.conf import settings
from PIL import Image, ImageOps

from .schema import JSON_SCHEMA, ExtractionError, parse_json_text, validate_payload

log = logging.getLogger(__name__)

MAX_SIDE = 1600

PROMPT = """You are reading a photo of a vocabulary page from an English or German textbook.
Extract every headword together with its definition exactly as printed on the page.

Rules:
- "language" is "en" if the words are English, "de" if German.
- "definition" must stay in the SAME language as the book (never translate it).
- For German nouns put the article (der/die/das) in "article" and the bare noun in "word";
  otherwise "article" is null.
- "part_of_speech": noun, verb, adjective, adverb, phrase, etc. (best guess, English labels).
- "translation_uz": a natural, accurate Uzbek translation of the word in Latin script.
- Skip page numbers, headings, exercises and example sentences that are not definitions.
- If the page has no word-definition pairs, return an empty "pairs" list.
Return ONLY the JSON object."""

MOCK_RESULTS = {
    "en": {
        "language": "en",
        "pairs": [
            {
                "word": "abundant",
                "definition": "existing in large quantities; more than enough",
                "part_of_speech": "adjective",
                "article": None,
                "translation_uz": "mo'l, serob",
            },
            {
                "word": "reluctant",
                "definition": "not willing to do something",
                "part_of_speech": "adjective",
                "article": None,
                "translation_uz": "istamaydigan, ikkilanuvchi",
            },
            {
                "word": "to borrow",
                "definition": "to take something from someone and promise to give it back",
                "part_of_speech": "verb",
                "article": None,
                "translation_uz": "qarzga olmoq",
            },
            {
                "word": "journey",
                "definition": "an act of travelling from one place to another",
                "part_of_speech": "noun",
                "article": None,
                "translation_uz": "sayohat, safar",
            },
            {
                "word": "to improve",
                "definition": "to become better or to make something better",
                "part_of_speech": "verb",
                "article": None,
                "translation_uz": "yaxshilamoq",
            },
            {
                "word": "ancient",
                "definition": "very old; from a long time ago",
                "part_of_speech": "adjective",
                "article": None,
                "translation_uz": "qadimiy",
            },
        ],
    },
    "de": {
        "language": "de",
        "pairs": [
            {
                "word": "Bahnhof",
                "definition": "ein Ort, an dem Züge halten und abfahren",
                "part_of_speech": "noun",
                "article": "der",
                "translation_uz": "vokzal",
            },
            {
                "word": "Wohnung",
                "definition": "Räume in einem Haus, in denen man lebt",
                "part_of_speech": "noun",
                "article": "die",
                "translation_uz": "kvartira, uy",
            },
            {
                "word": "Fahrrad",
                "definition": "ein Fahrzeug mit zwei Rädern, das man mit den Füßen bewegt",
                "part_of_speech": "noun",
                "article": "das",
                "translation_uz": "velosiped",
            },
            {
                "word": "einkaufen",
                "definition": "in Geschäften Dinge kaufen",
                "part_of_speech": "verb",
                "article": None,
                "translation_uz": "xarid qilmoq",
            },
            {
                "word": "pünktlich",
                "definition": "genau zur richtigen Zeit",
                "part_of_speech": "adjective",
                "article": None,
                "translation_uz": "o'z vaqtida",
            },
            {
                "word": "Rechnung",
                "definition": "ein Papier, auf dem steht, wie viel man bezahlen muss",
                "part_of_speech": "noun",
                "article": "die",
                "translation_uz": "hisob, chek",
            },
        ],
    },
}


def prepare_image(raw: bytes) -> tuple[bytes, str]:
    """Re-encode as JPEG, fix EXIF rotation, cap longest side at 1600px."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except Exception as exc:  # noqa: BLE001 - any decoder error means "not an image"
        raise ExtractionError("not_an_image") from exc
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


def _call_claude(image: bytes, media_type: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=2, timeout=120)
    response = client.beta.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": JSON_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image).decode(),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise ExtractionError("refused")
    return next((b.text for b in response.content if b.type == "text"), "")


def extract_with_llm(image: bytes, media_type: str, caller=_call_claude) -> dict:
    """Call the LLM, validate the JSON; retry once if invalid."""
    last: Exception | None = None
    for _attempt in range(2):
        try:
            return validate_payload(parse_json_text(caller(image, media_type)))
        except ExtractionError as exc:
            last = exc
            log.warning("LLM extraction invalid (%s), retrying", exc)
    raise ExtractionError(str(last) if last else "invalid_json")


# ---------------------------------------------------------------- fallback --
_LINE_SPLIT = re.compile(r"^\s*(?:\d+[.)]\s*)?(?P<word>[^\-–—:=]{1,60}?)\s*(?:[-–—:=]|\s{3,})\s*(?P<def>.{3,})$")
_POS = re.compile(r"^\(?(n|v|adj|adv|noun|verb|adjective|adverb)\.?\)?\s+", re.I)
_DE_HINTS = re.compile(r"\b(der|die|das|und|ist|ein|eine|nicht|mit)\b|[äöüß]", re.I)


def heuristic_parse(text: str, track_hint: str | None = None) -> dict:
    pairs = []
    for line in (text or "").splitlines():
        m = _LINE_SPLIT.match(line.strip())
        if not m:
            continue
        word, definition = m.group("word").strip(" .•*"), m.group("def").strip()
        pos = ""
        pm = _POS.match(definition)
        if pm:
            pos = pm.group(1).lower()
            definition = definition[pm.end() :]
        if len(word.split()) > 4 or len(definition) < 3:
            continue
        pairs.append(
            {"word": word, "definition": definition, "part_of_speech": pos, "article": None, "translation_uz": ""}
        )
    lang = track_hint if track_hint in ("en", "de") else ("de" if len(_DE_HINTS.findall(text or "")) > 3 else "en")
    return validate_payload({"language": lang, "pairs": pairs})


def extract_with_tesseract(image: bytes, track_hint: str | None = None) -> dict:
    import pytesseract

    img = Image.open(io.BytesIO(image))
    lang = "deu+eng" if track_hint == "de" else "eng+deu"
    try:
        text = pytesseract.image_to_string(img, lang=lang)
    except pytesseract.TesseractError:
        text = pytesseract.image_to_string(img)
    return heuristic_parse(text, track_hint)


def extract_pairs(raw: bytes, track_hint: str | None = None) -> dict:
    """Entry point used by the view. Returns {"language", "pairs", "engine"}."""
    image, media_type = prepare_image(raw)
    if settings.OCR_MOCK:
        data = json.loads(json.dumps(MOCK_RESULTS.get(track_hint or "en", MOCK_RESULTS["en"])))
        return {**validate_payload(data), "engine": "mock"}
    if settings.ANTHROPIC_API_KEY:
        try:
            return {**extract_with_llm(image, media_type), "engine": "claude"}
        except Exception as exc:  # noqa: BLE001 - fall back on any API/validation failure
            log.exception("Claude extraction failed, falling back to Tesseract: %s", exc)
    try:
        return {**extract_with_tesseract(image, track_hint), "engine": "tesseract"}
    except Exception as exc:  # noqa: BLE001
        log.exception("Tesseract failed: %s", exc)
        raise ExtractionError("ocr_unavailable") from exc
