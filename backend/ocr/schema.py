"""Strict validation of the extraction JSON returned by the LLM (or fallbacks)."""

from __future__ import annotations

import json
import re

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["en", "de"]},
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "definition": {"type": "string"},
                    "part_of_speech": {"type": "string"},
                    "article": {"anyOf": [{"type": "string", "enum": ["der", "die", "das"]}, {"type": "null"}]},
                    "translation_uz": {"type": "string"},
                },
                "required": ["word", "definition", "part_of_speech", "article", "translation_uz"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["language", "pairs"],
    "additionalProperties": False,
}


class ExtractionError(ValueError):
    pass


def _clean(s, limit: int) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        raise ExtractionError("field_not_string")
    return " ".join(s.split())[:limit]


def parse_json_text(text: str) -> dict:
    """Parse JSON from model text; tolerates ```json fences or prose around one object."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    elif not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ExtractionError("no_json_object")
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError("invalid_json") from exc
    return data


def validate_payload(data) -> dict:
    """Validate & normalise. Raises ExtractionError when the payload is unusable."""
    if not isinstance(data, dict):
        raise ExtractionError("not_an_object")
    lang = data.get("language")
    if lang not in ("en", "de"):
        raise ExtractionError("bad_language")
    pairs = data.get("pairs")
    if not isinstance(pairs, list):
        raise ExtractionError("pairs_not_list")
    out = []
    seen = set()
    for p in pairs:
        if not isinstance(p, dict):
            raise ExtractionError("pair_not_object")
        word = _clean(p.get("word"), 200)
        definition = _clean(p.get("definition"), 500)
        if not word or not definition:
            continue  # skip incomplete rows instead of failing the whole page
        article = p.get("article")
        article = article.lower().strip() if isinstance(article, str) else None
        if article not in ("der", "die", "das"):
            article = None
        if lang != "de":
            article = None
        # "der Hund" written in the word field -> split article out
        parts = word.split(maxsplit=1)
        if lang == "de" and len(parts) == 2 and parts[0].lower() in ("der", "die", "das"):
            article = article or parts[0].lower()
            word = parts[1]
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "word": word,
                "definition": definition,
                "part_of_speech": _clean(p.get("part_of_speech"), 30),
                "article": article,
                "translation_uz": _clean(p.get("translation_uz"), 300),
            }
        )
    return {"language": lang, "pairs": out[:100]}
