from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

from . import leitner
from .models import Pack, UserWord, Word, term_key

LEVELS = ["A1", "A2", "B1", "B2", "C1"]
UNLOCK_THRESHOLD = 70  # percent of previous level learned


def learned_keys(user, track: str) -> set[str]:
    return set(
        UserWord.objects.filter(user=user, track=track, box__gte=leitner.MAX_BOX).values_list("term_key", flat=True)
    )


def word_key(w: Word) -> str:
    return term_key(w.display)


def level_overview(user, track: str) -> list[dict]:
    learned = learned_keys(user, track)
    words = list(Word.objects.filter(track=track).only("id", "word", "article", "level", "pack_id"))
    by_level: dict[str, list[Word]] = {lv: [] for lv in LEVELS}
    for w in words:
        by_level.setdefault(w.level, []).append(w)
    packs = Pack.objects.filter(track=track).annotate(n=Count("words"))
    packs_by_level: dict[str, list[Pack]] = {}
    for p in packs:
        packs_by_level.setdefault(p.level, []).append(p)

    result = []
    prev_pct = 100
    for idx, lv in enumerate(LEVELS):
        lw = by_level.get(lv, [])
        n_learned = sum(1 for w in lw if word_key(w) in learned)
        pct = round(100 * n_learned / len(lw)) if lw else 0
        pack_rows = []
        for p in packs_by_level.get(lv, []):
            pw = [w for w in lw if w.pack_id == p.id]
            pl = sum(1 for w in pw if word_key(w) in learned)
            pack_rows.append(
                {
                    "id": p.id,
                    "slug": p.slug,
                    "emoji": p.emoji,
                    "name": {"uz": p.name_uz, "en": p.name_en, "ru": p.name_ru},
                    "total": len(pw),
                    "learned": pl,
                    "percent": round(100 * pl / len(pw)) if pw else 0,
                }
            )
        result.append(
            {
                "level": lv,
                "total": len(lw),
                "learned": n_learned,
                "percent": pct,
                "unlocked": idx == 0 or prev_pct >= UNLOCK_THRESHOLD,
                "packs": pack_rows,
            }
        )
        prev_pct = pct
    return result


def is_level_unlocked(user, track: str, level: str) -> bool:
    for row in level_overview(user, track):
        if row["level"] == level:
            return row["unlocked"]
    return False


def upsert_userword(
    user,
    track: str,
    term: str,
    *,
    translation_uz: str = "",
    definition: str = "",
    article: str = "",
    word: Word | None = None,
) -> UserWord:
    key = term_key(term)
    uw, created = UserWord.objects.get_or_create(
        user=user,
        track=track,
        term_key=key,
        defaults={
            "term": term.strip(),
            "translation_uz": translation_uz or "",
            "definition": definition or "",
            "article": article or "",
            "word": word,
        },
    )
    if not created:
        changed = False
        for field, val in (("translation_uz", translation_uz), ("definition", definition), ("article", article)):
            if val and not getattr(uw, field):
                setattr(uw, field, val)
                changed = True
        if word and not uw.word_id:
            uw.word = word
            changed = True
        if changed:
            uw.save()
    return uw


def record_answer(user, track: str, item: dict, correct: bool) -> tuple[UserWord, bool]:
    """Apply one answer to the Leitner system. Returns (userword, became_learned)."""
    word = None
    if item.get("word_id"):
        word = Word.objects.filter(pk=item["word_id"], track=track).first()
    uw = upsert_userword(
        user,
        track,
        item["term"],
        translation_uz=item.get("translation") or item.get("translation_uz") or "",
        definition=item.get("definition") or "",
        article=item.get("article") or "",
        word=word,
    )
    became = leitner.apply_to_userword(uw, correct, timezone.now())
    uw.save()
    return uw, became


def list_queryset(user, track: str, which: str):
    qs = UserWord.objects.filter(user=user, track=track)
    if which == "learned":
        return qs.filter(box__gte=leitner.MAX_BOX)
    if which == "missed":
        return qs.filter(box=leitner.MIN_BOX, miss_count__gt=0)
    if which == "want":
        return qs.filter(want_to_learn=True)
    if which == "due":
        return due_queryset(user, track)
    return qs.none()


def due_queryset(user, track: str):
    return UserWord.objects.filter(user=user, track=track, seen=True, due_at__lte=timezone.now())
