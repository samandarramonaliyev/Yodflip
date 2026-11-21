"""Load built-in vocabulary from words/seed/*.txt (idempotent).

File format (pipe-separated, UTF-8):
    ## slug | emoji | name_en | name_uz | name_ru         <- starts a themed pack
    word | pos | definition | translation_uz | example | example_uz
German nouns are written with their article ("der Hund"); it is split into Word.article.

Translations: words/seed/translations/{track}_{level}.txt, one line per word:
    word | ru | example_ru | other | example_other      (other = de for EN words, en for DE words)
Uzbek comes from the main file. Each translation is stored in WordTranslation(word, lang).

Idempotent and production-safe: words are matched by (track, word, article), so existing words
keep their IDs (and user progress). Words are never deleted. Every level must have exactly the
number of words in words.levels.LEVEL_SIZES.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from words.levels import LEVEL_SIZES, backfill_from_leitner
from words.models import Pack, Word, WordTranslation

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
TR_DIR = SEED_DIR / "translations"


def other_lang(track: str) -> str:
    return "de" if track == "en" else "en"


def parse_translations(path: Path) -> dict[str, dict]:
    """{raw word: {"ru": (text, example), "en"/"de": (text, example)}}"""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    track = path.stem.split("_")[0]
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) != 5:
            raise CommandError(f"translations/{path.name}:{n}: expected 5 columns, got {len(cols)}")
        out[cols[0]] = {"ru": (cols[1], cols[2]), other_lang(track): (cols[3], cols[4])}
    return out


def parse_file(path: Path) -> list[dict]:
    packs: list[dict] = []
    current: dict | None = None
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("##")):
            continue
        cols = [c.strip() for c in line.lstrip("#").split("|")]
        if line.startswith("##"):
            if len(cols) != 5:
                raise CommandError(f"{path.name}:{n}: pack header needs 5 columns")
            current = {
                "slug": cols[0],
                "emoji": cols[1],
                "name_en": cols[2],
                "name_uz": cols[3],
                "name_ru": cols[4],
                "words": [],
            }
            packs.append(current)
            continue
        if current is None:
            raise CommandError(f"{path.name}:{n}: word before first pack header")
        if len(cols) != 6 or not all(cols[:4]):
            raise CommandError(f"{path.name}:{n}: expected 6 columns, got {len(cols)}")
        current["words"].append(
            {
                "raw": cols[0],
                "pos": cols[1],
                "definition": cols[2],
                "translation_uz": cols[3],
                "example": cols[4],
                "example_uz": cols[5],
            }
        )
    return packs


def split_article(raw: str, track: str) -> tuple[str, str]:
    parts = raw.split(maxsplit=1)
    if track == "de" and len(parts) == 2 and parts[0] in ("der", "die", "das"):
        return parts[1], parts[0]
    return raw, ""


class Command(BaseCommand):
    help = "Seed built-in word levels (EN/DE, A1–C1). Skips when this exact seed was already loaded."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Reload even if the seed is unchanged.")

    def handle(self, *args, **opts):
        from core.models import SeedState

        files = sorted(SEED_DIR.glob("*_*.txt"))
        if not files:
            raise CommandError(f"No seed files in {SEED_DIR}")
        tr_files = sorted(TR_DIR.glob("*_*.txt"))
        digest = hashlib.sha256(
            b"".join(f.name.encode() + f.read_bytes() for f in files)
            + b"".join(b"tr/" + f.name.encode() + f.read_bytes() for f in tr_files)
        ).hexdigest()
        state = SeedState.objects.filter(key="words").first()
        if state and state.digest == digest and Word.objects.exists() and not opts["force"]:
            self.stdout.write("Seed unchanged, already loaded. Skipping (use --force to reload).")
            return
        total = 0
        with transaction.atomic():
            for path in files:
                track, level = path.stem.split("_")
                packs = parse_file(path)
                translations = parse_translations(TR_DIR / path.name)
                count = sum(len(p["words"]) for p in packs)
                if count != LEVEL_SIZES[level]:
                    raise CommandError(f"{path.name}: {count} words, expected exactly {LEVEL_SIZES[level]}")
                for order, p in enumerate(packs):
                    pack, _ = Pack.objects.update_or_create(
                        track=track,
                        level=level,
                        slug=p["slug"],
                        defaults={
                            "name_en": p["name_en"],
                            "name_uz": p["name_uz"],
                            "name_ru": p["name_ru"],
                            "emoji": p["emoji"],
                            "order": order,
                        },
                    )
                    for w in p["words"]:
                        word, article = split_article(w["raw"], track)
                        obj, _ = Word.objects.update_or_create(
                            track=track,
                            word=word,
                            article=article,
                            defaults={
                                "level": level,
                                "pack": pack,
                                "part_of_speech": w["pos"],
                                "definition": w["definition"],
                                "translation_uz": w["translation_uz"],
                                "example": w["example"],
                                "example_uz": w["example_uz"],
                            },
                        )
                        texts = {"uz": (w["translation_uz"], w["example_uz"]), **translations.get(w["raw"], {})}
                        for lang, (text, example) in texts.items():
                            if text and lang != track:
                                WordTranslation.objects.update_or_create(
                                    word=obj, lang=lang, defaults={"text": text, "example_translation": example}
                                )
                total += count
                self.stdout.write(f"  {path.name}: {count} words in {len(packs)} packs")
            SeedState.objects.update_or_create(key="words", defaults={"digest": digest})
            converted = backfill_from_leitner()
        self.stdout.write(self.style.SUCCESS(f"Seeded {total} words. Level progress backfilled: {converted}."))
