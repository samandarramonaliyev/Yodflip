"""Two-sided flashcards: "Topdim" / "Topa olmadim" with exact undo (server-side, idempotent).

* Topdim       -> Learned (box 5); removed from Want-to-learn and Missed.
                  Built-in level word: counts as found (once, never twice).
                  Deck card (owner): study_status = "known".
* Topa olmadim -> Want-to-learn; removed from Learned. Never reduces level progress.
                  Deck card (owner): study_status = "learning".
* Undo         -> restores the UserWord row (or removes it if the answer created it), the level
                  "found" mark if this answer set it, and the card status.
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from . import leitner
from .levels import check_completion, mark_found, settle_found
from .models import FlashAnswer, LevelRound, UserLevelWord, UserWord, Word, term_key
from .services import upsert_userword

SNAP_FIELDS = ("box", "correct_count", "miss_count", "seen", "want_to_learn", "due_at", "last_seen_at")


def _snapshot(uw: UserWord | None) -> dict:
    if uw is None:
        return {"existed": False}
    snap = {"existed": True}
    for f in SNAP_FIELDS:
        v = getattr(uw, f)
        snap[f] = v.isoformat() if isinstance(v, datetime) else v
    return snap


def list_flags(uw: UserWord | None) -> dict:
    return {
        "learned": bool(uw and uw.box >= leitner.MAX_BOX),
        "want": bool(uw and uw.want_to_learn),
        "missed": bool(uw and uw.box == leitner.MIN_BOX and uw.miss_count > 0),
    }


def answer(user, *, client_id: str, track: str, item: dict, known: bool, card_id=None, session_id=None) -> dict:
    with transaction.atomic():
        done = FlashAnswer.objects.filter(user=user, client_id=client_id).first()
        if done:
            return {**done.result, "answer_id": done.id, "duplicate": True}

        word = Word.objects.filter(pk=item.get("word_id"), track=track).first() if item.get("word_id") else None
        term = word.display if word else item["term"]
        before = UserWord.objects.select_for_update().filter(user=user, track=track, term_key=term_key(term)).first()
        snap = _snapshot(before)
        lang = item.get("translation_lang") or "uz"
        uw = upsert_userword(
            user,
            track,
            term,
            translation_uz=(word.translation_uz if word else (item.get("translation") if lang == "uz" else "")) or "",
            definition=(word.definition if word else item.get("definition")) or "",
            article=(word.article if word else item.get("article")) or "",
            word=word,
        )
        now = timezone.now()
        uw.seen = True
        uw.last_seen_at = now
        found_now = None
        if known:
            uw.box = leitner.MAX_BOX
            uw.want_to_learn = False
            uw.correct_count += 1
            uw.due_at = leitner.due_after(leitner.MAX_BOX, now)
            if word:
                rnd = None
                if session_id:
                    rnd = LevelRound.objects.filter(
                        session_id=session_id, user=user, word_ids__contains=word.id
                    ).first()
                if mark_found(user, word, rnd):
                    found_now = UserLevelWord.objects.get(user=user, word=word)
        else:
            uw.want_to_learn = True
            if uw.box >= leitner.MAX_BOX:
                uw.box = leitner.MIN_BOX
                uw.due_at = now
        uw.save()

        card = None
        prev_status = ""
        if card_id:
            from decks.models import Card

            card = Card.objects.filter(pk=card_id, deck__owner=user, deck__track=track).first()
            if card:
                prev_status = card.study_status
                card.study_status = "known" if known else "learning"
                card.save(update_fields=["study_status"])

        result = {"term": uw.term, "known": known, "lists": list_flags(uw), "level_found_now": bool(found_now)}
        if found_now:
            if word.level:
                row, completed_now, bonus = check_completion(user, word.track, word.level)
                result.update({"level_progress": row, "completed_now": completed_now, "bonus_xp": bonus})
            settle_found(user, [word])
        fa = FlashAnswer.objects.create(
            user=user,
            client_id=client_id,
            track=track,
            known=known,
            userword=uw,
            snapshot=snap,
            level_word=found_now,
            card=card,
            card_prev_status=prev_status,
            result=result,
        )
    return {**result, "answer_id": fa.id, "duplicate": False}


def undo(user, answer_id: int) -> dict:
    with transaction.atomic():
        fa = FlashAnswer.objects.select_for_update().filter(user=user, pk=answer_id).first()
        if fa is None:
            raise NotFound("answer_not_found")
        if fa.undone:
            return {"answer_id": fa.id, "undone": True, "lists": list_flags(fa.userword)}
        # "Bekor qilish" undoes the latest answer; snapshots of older answers may be outdated.
        uw = fa.userword
        snap = fa.snapshot or {}
        if uw is not None:
            if not snap.get("existed"):
                uw.delete()
                uw = None
            else:
                for f in SNAP_FIELDS:
                    v = snap.get(f)
                    if f in ("due_at", "last_seen_at") and v:
                        v = datetime.fromisoformat(v)
                    setattr(uw, f, v)
                uw.save()
        if fa.level_word_id:
            UserLevelWord.objects.filter(pk=fa.level_word_id).update(found_at=None, found_round=None)
        if fa.card_id:
            fa.card.study_status = fa.card_prev_status
            fa.card.save(update_fields=["study_status"])
        FlashAnswer.objects.filter(pk=fa.pk).update(undone=True, userword=uw)
    return {"answer_id": fa.id, "undone": True, "lists": list_flags(uw)}
