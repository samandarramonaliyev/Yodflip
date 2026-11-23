"""Words and questions of a quiz: due -> want to learn -> missed -> new words of the current level."""

from __future__ import annotations

import random
import re

from games.sources import item_from_userword, item_from_word
from words.leitner import MAX_BOX
from words.levels import progress
from words.models import UserLevelWord, Word, WordTranslation, term_key
from words.services import list_queryset

OPTIONS = 4
ARTICLES = ["der", "die", "das"]


def current_level(user, track: str) -> str | None:
    """The level chosen in the profile if it is open and unfinished, else the first open unfinished one."""
    rows = [r for r in progress(user, track) if r["unlocked"] and r["total"] and not r["completed"]]
    levels = [r["level"] for r in rows]
    cefr = user.cefr_for(track)
    return cefr if cefr in levels else (levels[0] if levels else None)


def _texts(word_ids, lang: str) -> dict[int, tuple[str, str]]:
    rows = WordTranslation.objects.filter(word_id__in=word_ids, lang=lang)
    return {r.word_id: (r.text, r.example_translation) for r in rows}


def pick_items(user, track: str, lang: str, count: int, rng: random.Random) -> list[dict]:
    chosen: list[dict] = []
    seen: set[str] = set()

    def add(items: list[dict]) -> None:
        need = [i["word_id"] for i in items if i["word_id"]]
        texts = _texts(need, lang)
        for i in items:
            if len(chosen) >= count:
                return
            key = term_key(i["term"])
            if key in seen:
                continue
            if i["word_id"] in texts:
                tr, ex = texts[i["word_id"]]
            elif lang == "uz":
                tr, ex = i["translation"], i["example_uz"]
            else:
                continue  # deck / scanned word without this language
            if not tr:
                continue
            seen.add(key)
            chosen.append({**i, "tr": tr, "ex_tr": ex})

    for which in ("due", "want", "missed"):
        qs = list_queryset(user, track, which).select_related("word").order_by("due_at", "id")
        if which != "due":
            qs = qs.filter(box__lt=MAX_BOX)  # already learned: no need to ask again
        rows = []
        for uw in qs[: count * 3]:
            item = item_from_userword(uw)
            if uw.word:
                item = {**item_from_word(uw.word), "term": uw.term}
            rows.append(item)
        add(rows)
    level = current_level(user, track) if len(chosen) < count else None
    if level:
        found = UserLevelWord.objects.filter(user=user, track=track, found_at__isnull=False).values("word_id")
        ids = list(Word.objects.filter(track=track, level=level).exclude(id__in=found).values_list("id", flat=True))
        rng.shuffle(ids)
        by_id = Word.objects.in_bulk(ids[: count * 2])
        add([item_from_word(by_id[i]) for i in ids[: count * 2] if i in by_id])
    return chosen


def _alts(text: str) -> set[str]:
    return {p.strip().lower() for p in re.split(r"[,/;]", re.sub(r"\(.*?\)", "", text or "")) if p.strip()}


def _options(answer: str, pool: list[str], rng: random.Random) -> list[str] | None:
    taken = _alts(answer)
    out = [answer]
    for p in rng.sample(pool, len(pool)):
        alts = _alts(p)
        if not alts or alts & taken:
            continue
        taken |= alts
        out.append(p)
        if len(out) == OPTIONS:
            rng.shuffle(out)
            return out
    return None


def build_questions(user, track: str, lang: str, count: int, rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random()
    items = pick_items(user, track, lang, count, rng)
    if not items:
        return []
    ids = list(
        Word.objects.filter(track=track, level__in=["A1", "A2", "B1"]).order_by("?").values_list("id", flat=True)[:60]
    )
    texts = _texts(ids, lang)
    words = Word.objects.in_bulk(ids)
    tr_pool = [i["tr"] for i in items] + [texts[i][0] for i in ids if i in texts]
    term_pool = [i["term"] for i in items] + [w.display for w in words.values()]
    out = []
    for n, i in enumerate(items):
        kind = "fwd" if n % 2 == 0 else "rev"  # mix of directions
        if track == "de" and i["article"] in ARTICLES and rng.random() < 0.3:
            kind = "art"
        if kind == "art":
            options, answer, prompt = ARTICLES, i["article"], i["word"]
        elif kind == "fwd":
            options, answer, prompt = _options(i["tr"], tr_pool, rng), i["tr"], i["term"]
        else:
            options, answer, prompt = _options(i["term"], term_pool, rng), i["term"], i["tr"]
        if not options:
            continue
        out.append(
            {
                "kind": kind,
                "prompt": prompt,
                "options": list(options),
                "answer": options.index(answer),
                "term": i["term"],
                "tr": i["tr"],
                "example": i["example"],
                "example_tr": i["ex_tr"],
                "item": {k: i[k] for k in ("term", "word_id", "article", "definition", "translation")},
            }
        )
    rng.shuffle(out)
    return out
