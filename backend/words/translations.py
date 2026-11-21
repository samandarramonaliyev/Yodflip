"""Translation language for memorization games.

Learning track EN → uz / ru / de; DE → uz / ru / en. Never a word into its own language.
Built-in words take the text from WordTranslation; deck cards use the deck's language; scanned
pairs and list items use what they have (items without the chosen language are left out).
"""

from __future__ import annotations

from rest_framework.exceptions import ValidationError

from .models import TRANSLATION_LANGS, WordTranslation

DIRECTIONS = ("forward", "reverse")


def resolve(track: str, lang: str | None, direction: str | None = None) -> tuple[str, str]:
    """Validate a (track, translation language, direction) choice. 400 on en→en, de→de, unknown codes."""
    lang = (lang or "uz").strip().lower()
    direction = (direction or "forward").strip().lower()
    if lang not in TRANSLATION_LANGS or lang == track:
        raise ValidationError({"translation_lang": "invalid_language_pair"})
    if direction not in DIRECTIONS:
        raise ValidationError({"direction": "invalid_direction"})
    return lang, direction


def apply_translations(items: list[dict], lang: str) -> list[dict]:
    """Return items whose "translation" is in `lang` (empty when that language is missing)."""
    ids = {i["word_id"] for i in items if i.get("word_id")}
    rows = {
        t.word_id: (t.text, t.example_translation) for t in WordTranslation.objects.filter(word_id__in=ids, lang=lang)
    }
    out = []
    for item in items:
        if item.get("word_id") in rows:
            text, example = rows[item["word_id"]]
            item = {**item, "translation": text, "example_tr": example, "translation_lang": lang}
        elif (item.get("translation_lang") or "uz") != lang:
            extra = (item.get("translations") or {}).get(lang, "")
            item = {**item, "translation": extra, "example_tr": "", "translation_lang": lang}
        out.append(item)
    return out


def available_langs(track: str, texts: list[dict]) -> list[str]:
    """Languages present in a list of {lang: text} dicts (e.g. a scanned set)."""
    found = {lang for t in texts for lang, v in t.items() if v}
    return [lang for lang in TRANSLATION_LANGS if lang != track and lang in found]
