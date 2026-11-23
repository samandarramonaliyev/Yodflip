"""Level progress: FOUND = LEARNED, computed on the server from UserLevelWord rows.

Rules (apply to every game played inside a level):
* The first correct answer for a level word marks it found, permanently (Learned list, not Missed).
* A found word is never counted twice: no progress, no XP, no penalty on later answers.
* Rounds prefer unfound words, never repeat a word inside a round and avoid the words of the
  user's last 2 rounds. Found words fill a board only when unfound words run out, as
  "review fillers", at most 2 times per word. Fillers change nothing.
* Missed words stay in the pool and go to the Missed list (no progress penalty).
* Next level unlocks at 70% found. 100% gives a one-time completion bonus.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.db.models import Count, F
from django.utils import timezone

from . import leitner
from .models import LevelAnswer, LevelCompletion, LevelRound, Pack, UserLevelWord, UserWord, Word

LEVELS = ["A1", "A2", "B1", "B2", "C1"]
LEVEL_SIZES = {"A1": 100, "A2": 150, "B1": 200, "B2": 250, "C1": 300}
UNLOCK_PERCENT = 70
COMPLETION_BONUS_XP = 200
MIN_ROUND = 3
MAX_ROUND = 60
RECENT_ROUNDS = 2


def unlock_target(total: int) -> int:
    """Found words needed to unlock the next level: ceil(70% of total)."""
    return (total * UNLOCK_PERCENT + 99) // 100


def _row(level: str, total: int, found: int, unlocked: bool) -> dict:
    target = unlock_target(total)
    return {
        "level": level,
        "total": total,
        "found": found,
        "learned": found,  # kept for older clients
        "remaining": max(0, total - found),
        "percent": (100 * found // total) if total else 0,
        "unlock_target": target,
        "to_unlock": max(0, target - found),
        "unlocked": unlocked,
        "completed": total > 0 and found >= total,
    }


def progress(user, track: str, with_packs: bool = False) -> list[dict]:
    totals = dict(
        Word.objects.filter(track=track).values_list("level").annotate(n=Count("id")).values_list("level", "n")
    )
    found = dict(
        UserLevelWord.objects.filter(user=user, track=track, found_at__isnull=False)
        .values_list("level")
        .annotate(n=Count("id"))
        .values_list("level", "n")
    )
    pack_rows: dict[str, list[dict]] = {}
    if with_packs:
        found_by_pack = dict(
            UserLevelWord.objects.filter(user=user, track=track, found_at__isnull=False)
            .values_list("word__pack_id")
            .annotate(n=Count("id"))
            .values_list("word__pack_id", "n")
        )
        for p in Pack.objects.filter(track=track).annotate(n=Count("words")).order_by("level", "order"):
            f = found_by_pack.get(p.id, 0)
            pack_rows.setdefault(p.level, []).append(
                {
                    "id": p.id,
                    "slug": p.slug,
                    "emoji": p.emoji,
                    "name": {"uz": p.name_uz, "en": p.name_en, "ru": p.name_ru},
                    "total": p.n,
                    "found": f,
                    "learned": f,
                    "percent": (100 * f // p.n) if p.n else 0,
                }
            )
    rows = []
    prev: dict | None = None
    for lv in LEVELS:
        unlocked = prev is None or prev["found"] >= prev["unlock_target"]
        row = _row(lv, totals.get(lv, 0), found.get(lv, 0), unlocked)
        if with_packs:
            row["packs"] = pack_rows.get(lv, [])
        rows.append(row)
        prev = row
    return rows


def level_progress(user, track: str, level: str) -> dict:
    for row in progress(user, track):
        if row["level"] == level:
            return row
    raise ValueError("invalid_level")


def is_unlocked(user, track: str, level: str) -> bool:
    return level in LEVELS and level_progress(user, track, level)["unlocked"]


# --------------------------------------------------------------------------- rounds
@dataclass
class Round:
    session_id: str | None
    words: list[Word] = field(default_factory=list)
    filler_ids: set[int] = field(default_factory=set)
    completed: bool = False  # the whole level is found
    pool_done: bool = False  # the chosen pack / game filter has no unfound words left


def _usable_qs(track: str, level: str, game: str = "", pack: str = ""):
    qs = Word.objects.filter(track=track, level=level)
    if pack:
        qs = qs.filter(pack__slug=pack)
    if game == "derdiedas":
        qs = qs.filter(article__in=["der", "die", "das"])
    return qs


def build_round(
    user, track: str, level: str, size: int, *, game: str = "", pack: str = "", rng: random.Random | None = None
) -> Round:
    rng = rng or random.Random()
    size = max(MIN_ROUND, min(MAX_ROUND, size))
    states = {
        r["word_id"]: r
        for r in UserLevelWord.objects.filter(user=user, track=track, level=level).values(
            "word_id", "found_at", "filler_uses"
        )
    }
    level_ids = list(Word.objects.filter(track=track, level=level).values_list("id", flat=True))
    if level_ids and all(states.get(i, {}).get("found_at") for i in level_ids):
        return Round(session_id=None, completed=True)

    pool = list(_usable_qs(track, level, game, pack).values_list("id", flat=True))
    recent: set[int] = set()
    for ids in LevelRound.objects.filter(user=user, track=track, level=level).values_list("word_ids", flat=True)[
        :RECENT_ROUNDS
    ]:
        recent.update(ids)

    def fresh_first(ids: list[int]) -> list[int]:
        rng.shuffle(ids)
        return [i for i in ids if i not in recent] + [i for i in ids if i in recent]

    unfound = fresh_first([i for i in pool if not states.get(i, {}).get("found_at")])
    if not unfound:
        return Round(session_id=None, pool_done=True)
    chosen = unfound[:size]
    fillers: list[int] = []
    if len(chosen) < size:
        candidates = [
            i
            for i in pool
            if states.get(i, {}).get("found_at") and states[i]["filler_uses"] < UserLevelWord.MAX_FILLER_USES
        ]
        fillers = fresh_first(candidates)[: size - len(chosen)]
    ids = chosen + fillers
    rng.shuffle(ids)

    now = timezone.now()
    with transaction.atomic():
        rnd = LevelRound.objects.create(
            session_id=uuid.uuid4().hex,
            user=user,
            track=track,
            level=level,
            game=game[:30],
            word_ids=ids,
            filler_ids=fillers,
        )
        UserLevelWord.objects.bulk_create(
            [UserLevelWord(user=user, word_id=i, track=track, level=level) for i in chosen if i not in states],
            ignore_conflicts=True,
        )
        UserLevelWord.objects.filter(user=user, word_id__in=ids).update(last_shown_at=now)
    by_id = Word.objects.select_related("pack").in_bulk(ids)
    return Round(session_id=rnd.session_id, words=[by_id[i] for i in ids if i in by_id], filler_ids=set(fillers))


# -------------------------------------------------------------------------- answers
def _mark_learned(user, w: Word, now) -> None:
    from .services import upsert_userword

    uw = upsert_userword(
        user, w.track, w.display, translation_uz=w.translation_uz, definition=w.definition, article=w.article, word=w
    )
    uw.box = leitner.MAX_BOX
    uw.correct_count += 1
    uw.seen = True
    uw.last_seen_at = now
    uw.due_at = leitner.due_after(leitner.MAX_BOX, now)
    uw.save()


def _mark_missed(user, w: Word, now) -> None:
    from .services import upsert_userword

    uw = upsert_userword(
        user, w.track, w.display, translation_uz=w.translation_uz, definition=w.definition, article=w.article, word=w
    )
    if uw.box >= leitner.MAX_BOX:
        return  # learned elsewhere (deck / list): a level miss doesn't demote it
    uw.box = leitner.MIN_BOX
    uw.miss_count += 1
    uw.seen = True
    uw.last_seen_at = now
    uw.due_at = now
    uw.save()


def record_answers(user, rnd: LevelRound, answers: list[tuple[int, bool]]) -> dict:
    """Apply answers of one round. Idempotent: retries and duplicates never double-count."""
    now = timezone.now()
    round_ids = set(rnd.word_ids)
    fillers = set(rnd.filler_ids)
    new_found: list[int] = []
    ignored = 0
    words = Word.objects.in_bulk({wid for wid, _ in answers if wid in round_ids})
    with transaction.atomic():
        for word_id, correct in answers:
            w = words.get(word_id)
            if w is None:
                ignored += 1
                continue
            try:
                with transaction.atomic():
                    _, first = LevelAnswer.objects.get_or_create(round=rnd, word=w, defaults={"correct": correct})
            except IntegrityError:
                first = False
            if word_id in fillers:
                if first:
                    UserLevelWord.objects.filter(
                        user=user, word=w, filler_uses__lt=UserLevelWord.MAX_FILLER_USES
                    ).update(filler_uses=F("filler_uses") + 1)
                continue  # fillers: no XP, no progress, no penalty, no list change
            if correct:
                UserLevelWord.objects.get_or_create(user=user, word=w, defaults={"track": w.track, "level": w.level})
                updated = UserLevelWord.objects.filter(user=user, word=w, found_at__isnull=True).update(
                    found_at=now, found_round=rnd
                )
                if updated:
                    new_found.append(word_id)
                    _mark_learned(user, w, now)
                if not first:
                    LevelAnswer.objects.filter(round=rnd, word=w).update(correct=True)
            elif first and not UserLevelWord.objects.filter(user=user, word=w, found_at__isnull=False).exists():
                _mark_missed(user, w, now)

        row, completed_now, bonus = check_completion(user, rnd.track, rnd.level)
    return {
        "session_id": rnd.session_id,
        "new_found": new_found,
        "new_found_count": len(new_found),
        "ignored": ignored,
        "progress": row,
        "completed_now": completed_now,
        "bonus_xp": bonus,
    }


def check_completion(user, track: str, level: str) -> tuple[dict, bool, int]:
    """(progress row, completed just now, bonus XP). The bonus is given exactly once per level."""
    from gamification.services import grant, record_activity

    row = level_progress(user, track, level)
    if not row["completed"]:
        return row, False, 0
    try:
        with transaction.atomic():
            LevelCompletion.objects.create(user=user, track=track, level=level, bonus_xp=COMPLETION_BONUS_XP)
    except IntegrityError:
        return row, False, 0
    user.refresh_from_db()
    record_activity(user, COMPLETION_BONUS_XP, 0, 0, games=0)
    grant(user, "level_complete")
    return row, True, COMPLETION_BONUS_XP


def settle_found(user, words: list[Word]) -> None:
    """After words were found outside a round of their own level: level completion bonuses."""
    for track, level in {(w.track, w.level) for w in words if w.level}:
        check_completion(user, track, level)


def mark_found(user, w: Word, rnd: LevelRound | None = None) -> bool:
    """Mark a built-in word found (FOUND = LEARNED). True only the first time."""
    UserLevelWord.objects.get_or_create(user=user, word=w, defaults={"track": w.track, "level": w.level})
    return bool(
        UserLevelWord.objects.filter(user=user, word=w, found_at__isnull=True).update(
            found_at=timezone.now(), found_round=rnd
        )
    )


def found_words(user, track: str, level: str):
    return (
        Word.objects.filter(track=track, level=level, level_progress__user=user, level_progress__found_at__isnull=False)
        .select_related("pack")
        .order_by("-level_progress__found_at")
    )


# ------------------------------------------------------------------------- backfill
def backfill_from_leitner(users=None) -> int:
    """Turn Leitner-learned (box 5) built-in words into found level words. Idempotent."""
    from .models import term_key

    qs = UserWord.objects.filter(box__gte=leitner.MAX_BOX)
    if users is not None:
        qs = qs.filter(user__in=users)
    index: dict[tuple[str, str], Word] = {}
    for w in Word.objects.only("id", "track", "level", "word", "article"):
        index[(w.track, term_key(w.display))] = w
    by_id = {w.id: w for w in index.values()}
    rows = []
    now = timezone.now()
    for uw in qs.only("user_id", "track", "term_key", "word_id", "last_seen_at").iterator():
        w = by_id.get(uw.word_id) if uw.word_id else None
        w = w or index.get((uw.track, uw.term_key))
        if w is None:
            continue
        rows.append(
            UserLevelWord(user_id=uw.user_id, word=w, track=w.track, level=w.level, found_at=uw.last_seen_at or now)
        )
    if not rows:
        return 0
    before = UserLevelWord.objects.filter(found_at__isnull=False).count()
    pending = set(UserLevelWord.objects.filter(found_at__isnull=True).values_list("user_id", "word_id"))
    UserLevelWord.objects.bulk_create(rows, ignore_conflicts=True, batch_size=1000)
    # Rows that existed (shown, not found yet) but are learned in Leitner: mark found too.
    for r in rows:
        if (r.user_id, r.word.id) in pending:
            UserLevelWord.objects.filter(user_id=r.user_id, word=r.word, found_at__isnull=True).update(
                found_at=r.found_at
            )
    return UserLevelWord.objects.filter(found_at__isnull=False).count() - before


__all__ = [
    "LEVELS",
    "LEVEL_SIZES",
    "UNLOCK_PERCENT",
    "COMPLETION_BONUS_XP",
    "unlock_target",
    "progress",
    "level_progress",
    "is_unlocked",
    "build_round",
    "record_answers",
    "found_words",
    "backfill_from_leitner",
]
