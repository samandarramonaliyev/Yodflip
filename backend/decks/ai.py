"""LLM translation of deck cards into another language. Results are cached on the cards."""

from __future__ import annotations

import json
import logging

from django.conf import settings

log = logging.getLogger(__name__)

LANG_NAMES = {"uz": "Uzbek (Latin script)", "ru": "Russian (Cyrillic)", "en": "English", "de": "German"}


class AIUnavailable(RuntimeError):
    """No API key, or the API failed: generate nothing new."""


def _call_claude(prompt: str, schema: dict) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=2, timeout=60)
    response = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=8000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise AIUnavailable("refused")
    return next((b.text for b in response.content if b.type == "text"), "")


def translate_terms(track: str, lang: str, rows: list[tuple[str, str, str]], caller=None) -> list[str]:
    """rows: (term, known translation, its language). Returns one translation per row ("" if unknown)."""
    if not settings.ANTHROPIC_API_KEY and caller is None:
        raise AIUnavailable("no_api_key")
    schema = {
        "type": "object",
        "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
        "required": ["translations"],
        "additionalProperties": False,
    }
    lines = "\n".join(
        f"{i + 1}. {term} (= {known} in {LANG_NAMES.get(kl, kl)})" for i, (term, known, kl) in enumerate(rows)
    )
    prompt = (
        f"Translate these {LANG_NAMES['en' if track == 'en' else 'de']} vocabulary words into {LANG_NAMES[lang]}. "
        "Give the most common meaning first, at most two short alternatives separated by ', '. "
        "German nouns get their article. Return exactly one translation per line, in order, as JSON.\n\n" + lines
    )
    try:
        text = (caller or _call_claude)(prompt, schema)
        data = json.loads(text)
        out = [" ".join(str(t).split()) for t in data.get("translations", [])]
    except AIUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - any API / parsing problem means "not available"
        log.warning("deck translation failed: %s", exc)
        raise AIUnavailable("api_error") from exc
    return (out + [""] * len(rows))[: len(rows)]
