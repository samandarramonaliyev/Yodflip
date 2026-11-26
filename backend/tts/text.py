"""What is actually spoken: no UI symbols, brackets or alternative forms."""

from __future__ import annotations

import re
import unicodedata

ARTICLE = re.compile(r"^(der|die|das)\s", re.I)


def spoken_text(text: str, lang: str) -> str:
    s = unicodedata.normalize("NFC", text or "")
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}|<[^>]*>", " ", s)
    s = re.sub(r"[“”„«»\"*_#|•→←↔=~^`]", " ", s)
    s = "".join(" " if unicodedata.category(c) in ("So", "Sk", "Cs", "Co", "Cf") else c for c in s)
    s = " ".join(s.split())
    sentence = bool(re.search(r"[.!?…]$", s))
    if sentence:
        s = re.sub(r"\s*/\s*", ", ", s)
    else:
        s = re.split(r"\s*[/;]\s*", s)[0] if re.split(r"\s*[/;]\s*", s)[0] else s
        parts = [p.strip() for p in s.split(",")]
        if lang == "de" and len(parts) > 1 and ARTICLE.match(parts[0]) and ARTICLE.match(parts[1]):
            s = parts[0]  # "der Arzt, die Ärztin": the main form
        elif lang == "de" and len(parts) > 1 and ARTICLE.match(parts[0]) and parts[1].startswith("-"):
            s = parts[0]  # "der Lehrer, -in"
    return " ".join(s.split()).strip(" ,;/-")


def kind_of(text: str) -> str:
    """'sentence' (ends with . ! ? … or is long) or 'word' (a word or short phrase, e.g. 'der Bahnhof')."""
    s = (text or "").strip()
    return "sentence" if re.search(r"[.!?…]$", s) or len(s.split()) > 4 else "word"
