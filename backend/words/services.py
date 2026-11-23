from __future__ import annotations

from django.utils import timezone

from . import leitner
from .models import UserWord, Word, term_key

LEVELS = ["A1", "A2", "B1", "B2", "C1"]
UNLOCK_THRESHOLD = 70  # percent of previous level found


def level_overview(user, track: str) -> list[dict]:
    """Level progress per level (server-side, from found words). See words/levels.py."""
    from .levels import progress

    return progress(user, track, with_packs=True)


def is_level_unlocked(user, track: str, level: str) -> bool:
    from .levels import is_unlocked

    return is_unlocked(user, track, level)


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


def apply_answer(user, track: str, item: dict, correct: bool) -> bool:
    """One answer outside a level round (duel, bot quiz, exam simulation). True if a word was found now.

    Built-in word not found yet: the level rules apply (found = learned, counted once; a miss goes to
    Missed). Everything else (found words, deck / scanned words): the normal Leitner step.
    """
    from . import levels
    from .models import UserLevelWord

    word = Word.objects.filter(pk=item["word_id"], track=track).first() if item.get("word_id") else None
    if word is None or UserLevelWord.objects.filter(user=user, word=word, found_at__isnull=False).exists():
        record_answer(user, track, item, correct)
        return False
    if not correct:
        levels._mark_missed(user, word, timezone.now())
        return False
    if not levels.mark_found(user, word):
        return False
    levels._mark_learned(user, word, timezone.now())
    levels.settle_found(user, [word])
    return True


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
