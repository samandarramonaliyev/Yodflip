"""Exam pack seed files: parsing and checks (no database needed).

exams/seed/<slug>.txt
    ## slug | emoji | name_en | name_uz | name_ru            <- topic
    = der Tag; die Woche                                     <- words that already exist in the track
    word | pos | definition | uz | ru | other | example | example_uz | example_ru | example_other
(other = de for English words, en for German words; German nouns carry their article.)
exams/seed/extra/<slug>.txt (IELTS):  word | collocation; collocation | word family (optional)

The lists are original: common, exam-relevant vocabulary by topic. Not copied from official lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from words.management.commands.seed_words import parse_file, parse_translations
from words.models import term_key
from words.seedcheck import SEED_DIR as LEVEL_DIR
from words.seedcheck import same_as_source

SEED_DIR = Path(__file__).resolve().parent / "seed"
FIELDS = (
    "raw", "pos", "definition", "uz", "ru", "other", "example", "example_uz", "example_ru", "example_other",
)  # fmt: skip


@dataclass(frozen=True)
class PackInfo:
    slug: str
    track: str
    count: int
    emoji: str
    name_uz: str
    name_en: str
    name_ru: str
    extra: bool = False  # collocations required


PACKS = [
    PackInfo("goethe-a1", "de", 300, "🇩🇪", "Goethe A1 tayyorlov", "Goethe A1 prep", "Подготовка к Goethe A1"),
    PackInfo("goethe-a2", "de", 400, "🥨", "Goethe A2 tayyorlov", "Goethe A2 prep", "Подготовка к Goethe A2"),
    PackInfo("goethe-b1", "de", 500, "🏰", "Goethe B1 tayyorlov", "Goethe B1 prep", "Подготовка к Goethe B1"),
    PackInfo(
        "ielts-academic",
        "en",
        500,
        "🎓",
        "IELTS Academic so'zlari",
        "IELTS Academic words",
        "Слова IELTS Academic",
        True,
    ),
    PackInfo(
        "core-1000", "en", 1000, "🔑", "Eng kerakli 1000 so'z (Core 1000)", "Core 1000 words", "1000 самых нужных слов"
    ),
]


@dataclass
class ParsedPack:
    info: PackInfo
    topics: list[dict] = field(default_factory=list)  # {slug, emoji, name_*, words: [raw]}
    new: dict[str, dict] = field(default_factory=dict)  # key -> full row
    extra: dict[str, tuple[str, str]] = field(default_factory=dict)  # key -> (collocations, family)


def parse_pack(info: PackInfo, errors: list[str], seed_dir: Path = SEED_DIR) -> ParsedPack:
    out = ParsedPack(info)
    path = seed_dir / f"{info.slug}.txt"
    if not path.exists():
        errors.append(f"{path.name}: missing")
        return out
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("##")):
            continue
        where = f"{path.name}:{n}"
        if line.startswith("##"):
            cols = [c.strip() for c in line.lstrip("#").split("|")]
            if len(cols) != 5 or not all(cols):
                errors.append(f"{where}: topic header needs 5 columns")
                continue
            keys = ("slug", "emoji", "name_en", "name_uz", "name_ru")
            out.topics.append({**dict(zip(keys, cols, strict=True)), "words": []})
            continue
        if not out.topics:
            errors.append(f"{where}: word before the first topic")
            continue
        words = out.topics[-1]["words"]
        if line.startswith("="):
            words += [w.strip() for w in line[1:].split(";") if w.strip()]
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) != len(FIELDS):
            errors.append(f"{where}: expected {len(FIELDS)} columns, got {len(cols)}: {cols[0]!r}")
            continue
        row = dict(zip(FIELDS, cols, strict=True))
        empty = [f for f in FIELDS if not row[f]]
        if empty:
            errors.append(f"{where}: {row['raw']!r} has empty {', '.join(empty)}")
        key = term_key(row["raw"])
        if key in out.new:
            errors.append(f"{where}: {row['raw']!r} is defined twice")
        out.new[key] = row
        words.append(row["raw"])
    extra = seed_dir / "extra" / f"{info.slug}.txt"
    if info.extra and extra.exists():
        for n, raw in enumerate(extra.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip() or raw.startswith("#"):
                continue
            cols = [c.strip() for c in raw.split("|")]
            if len(cols) not in (2, 3) or not cols[1]:
                errors.append(f"extra/{extra.name}:{n}: expected word | collocations | family")
                continue
            out.extra[term_key(cols[0])] = (cols[1], cols[2] if len(cols) == 3 else "")
    return out


def level_words() -> dict[str, dict[str, dict]]:
    """{track: {key: {raw, pos, uz, ru, other, ...}}} of the built-in level vocabulary."""
    out: dict[str, dict[str, dict]] = {"en": {}, "de": {}}
    for path in sorted(LEVEL_DIR.glob("*_*.txt")):
        track = path.stem.split("_")[0]
        tr = parse_translations(LEVEL_DIR / "translations" / path.name)
        for p in parse_file(path):
            for w in p["words"]:
                out[track][term_key(w["raw"])] = {**w, "translations": tr.get(w["raw"], {})}
    return out


def load_all(seed_dir: Path = SEED_DIR) -> tuple[list[ParsedPack], list[str]]:
    errors: list[str] = []
    packs = [parse_pack(i, errors, seed_dir) for i in PACKS]
    return packs, errors


def check(seed_dir: Path = SEED_DIR) -> tuple[dict[str, int], list[str]]:
    packs, errors = load_all(seed_dir)
    levels = level_words()
    counts: dict[str, int] = {}
    owners: dict[tuple[str, str], str] = {}
    for p in packs:
        for key, row in p.new.items():
            name = f"{p.info.slug}: {row['raw']!r}"
            if key in levels[p.info.track]:
                errors.append(f"{name} already exists in a level: link it with '='")
            if (p.info.track, key) in owners:
                errors.append(f"{name} is already defined in {owners[p.info.track, key]}: link it with '='")
            owners[p.info.track, key] = p.info.slug
            for f in ("uz", "ru", "other"):
                if same_as_source(row[f], row["raw"]):
                    errors.append(f"{name}: {f} translation equals the word")
            for f in ("example_uz", "example_ru", "example_other"):
                if same_as_source(row[f], row["example"]):
                    errors.append(f"{name}: {f} equals the example")
            if p.info.track == "de" and row["pos"] == "noun" and row["raw"].split()[0] not in ("der", "die", "das"):
                errors.append(f"{name}: German noun without article")
            if row["ru"] and not any(
                "а" <= c.lower() <= "я" or c.lower() == "ё" for c in row["ru"] + row["example_ru"]
            ):
                errors.append(f"{name}: Russian text without Cyrillic letters")
            if any(len(row[f]) > 200 for f in ("uz", "ru", "other")) or len(row["definition"]) > 300:
                errors.append(f"{name}: text too long")
    for p in packs:
        seen: set[str] = set()
        slugs: set[str] = set()
        for t in p.topics:
            if t["slug"] in slugs:
                errors.append(f"{p.info.slug}: duplicate topic {t['slug']}")
            slugs.add(t["slug"])
            if not t["words"]:
                errors.append(f"{p.info.slug}: empty topic {t['slug']}")
            for raw in t["words"]:
                key = term_key(raw)
                if key in seen:
                    errors.append(f"{p.info.slug}: duplicate {raw!r}")
                seen.add(key)
                if key not in levels[p.info.track] and (p.info.track, key) not in owners:
                    errors.append(f"{p.info.slug}: unknown word {raw!r}")
                if p.info.extra and key not in p.extra:
                    errors.append(f"{p.info.slug}: no collocations for {raw!r}")
        errors += [f"{p.info.slug}: collocations for unknown word {k!r}" for k in p.extra if k not in seen]
        counts[p.info.slug] = len(seen)
        if len(seen) != p.info.count:
            errors.append(f"{p.info.slug}: {len(seen)} words, expected exactly {p.info.count}")
    return counts, errors
