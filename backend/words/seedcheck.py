"""Validation of the built-in vocabulary files (no database needed).

Checks: exact word count per level and track, no duplicate word inside a track (so every word
belongs to exactly one level), no empty fields, German nouns carry der/die/das, unique pack slugs.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .levels import LEVEL_SIZES
from .models import term_key

SEED_DIR = Path(__file__).resolve().parent / "seed"
FIELDS = ("raw", "pos", "definition", "translation_uz", "example", "example_uz")


def check_seed(seed_dir: Path = SEED_DIR) -> tuple[dict[str, dict[str, int]], list[str]]:
    from words.management.commands.seed_words import parse_file

    counts: dict[str, dict[str, int]] = {}
    errors: list[str] = []
    seen: dict[str, dict[str, str]] = {}
    for track in ("en", "de"):
        counts[track] = {}
        seen[track] = {}
        for level, size in LEVEL_SIZES.items():
            path = seed_dir / f"{track}_{level}.txt"
            if not path.exists():
                errors.append(f"{path.name}: missing")
                continue
            try:
                packs = parse_file(path)
            except Exception as e:  # noqa: BLE001 - report every problem
                errors.append(str(e))
                continue
            slugs = Counter(p["slug"] for p in packs)
            errors += [f"{path.name}: duplicate pack slug {s}" for s, n in slugs.items() if n > 1]
            n = 0
            for p in packs:
                for w in p["words"]:
                    n += 1
                    empty = [f for f in FIELDS if not w[f].strip()]
                    if empty:
                        errors.append(f"{path.name}: {w['raw']!r} has empty {', '.join(empty)}")
                    key = term_key(w["raw"])
                    if "(" in w["raw"] or ")" in w["raw"]:
                        errors.append(f"{path.name}: brackets in the word itself: {w['raw']!r}")
                    if track == "de" and w["pos"] == "noun" and w["raw"].split()[0] not in ("der", "die", "das"):
                        errors.append(f"{path.name}: German noun without article: {w['raw']!r}")
                    if key in seen[track]:
                        errors.append(f"{path.name}: duplicate {w['raw']!r} (also in {seen[track][key]})")
                    else:
                        seen[track][key] = level
            counts[track][level] = n
            if n != size:
                errors.append(f"{path.name}: {n} words, expected exactly {size}")
    return counts, errors
