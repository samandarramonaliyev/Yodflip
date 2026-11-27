"""Duel rules: start / answer / finish / result / rewards / expiry / rematch / referrals."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from accounts.models import User

from .models import Duel, DuelParticipant
from .questions import build_questions, load_items

LIFETIME = timedelta(hours=48)
MIN_ANSWER_MS = 300
STALE_START = timedelta(minutes=30)  # an opponent who left without finishing frees the place after this
XP = {"win": 30, "draw": 15, "loss": 10}


class Conflict(APIException):
    status_code = 409


class Gone(APIException):
    status_code = 410


# --------------------------------------------------------------------------- links
def duel_path(code: str) -> str:
    return f"/duel/{code}"


def web_link(code: str) -> str:
    return f"{settings.PUBLIC_URL.rstrip('/')}{duel_path(code)}"


def telegram_link(code: str) -> str:
    """Mini App deep link. Without a short name: /start deep link (the bot answers with a Web App button)."""
    bot, app = settings.TELEGRAM_BOT_USERNAME, settings.TELEGRAM_APP_SHORT_NAME
    if not bot:
        return ""
    if app:
        return f"https://t.me/{bot}/{app}?startapp=duel_{code}"
    return f"https://t.me/{bot}?start=duel_{code}"


def code_from_param(param: str | None) -> str:
    """'duel_AbC123' → 'AbC123' ('' for anything else)."""
    p = (param or "").strip()
    code = p[5:] if p.startswith("duel_") else ""
    return code if code.isascii() and code.isalnum() and len(code) <= 16 else ""


# --------------------------------------------------------------------------- create / load
def create(user, *, track, source, ref, mode, lang, trusted=False, rematch_of=None) -> Duel:
    items, label, lang = load_items(
        user, track=track, source=source, ref=str(ref), mode=mode, lang=lang, trusted=trusted
    )
    return Duel.objects.create(
        creator=user,
        track=track,
        source=source,
        source_ref=str(ref),
        source_label=label[:120],
        mode=mode,
        translation_lang=lang,
        words=build_questions(items, mode),
        rematch_of=rematch_of,
        expires_at=timezone.now() + LIFETIME,
    )


def get(code: str) -> Duel:
    duel = Duel.objects.select_related("creator").filter(code=code).first()
    if duel is None:
        raise NotFound("duel_not_found")
    if duel.status in (Duel.PENDING, Duel.OPEN) and duel.expires_at <= timezone.now():
        expire(duel)
    return duel


def participant_for(duel: Duel, user, guest_token: str = "", lock: bool = False) -> DuelParticipant | None:
    qs = DuelParticipant.objects.filter(duel=duel)
    if lock:
        qs = qs.select_for_update()
    if user is not None:
        p = qs.filter(user=user).first()
        if p:
            return p
    if guest_token:
        return qs.filter(user__isnull=True, guest_token=guest_token).first()
    return None


def start(duel: Duel, user, guest_token: str = "") -> DuelParticipant:
    """Join (or resume). Exactly one opponent per code."""
    mine = participant_for(duel, user, guest_token)
    if duel.status == Duel.EXPIRED and not (mine and mine.finished_at):
        raise Gone("duel_expired")
    if mine:
        return mine
    now = timezone.now()
    if user is not None and user.pk == duel.creator_id:
        role = DuelParticipant.CREATOR
    else:
        role = DuelParticipant.OPPONENT
        if duel.status == Duel.PENDING:
            raise Conflict("creator_not_finished")
        if duel.status == Duel.COMPLETED:
            raise Conflict("duel_taken")
    try:
        with transaction.atomic():
            if role == DuelParticipant.OPPONENT:
                # Free the place of somebody who started, left and never finished.
                DuelParticipant.objects.filter(
                    duel=duel, role=role, finished_at__isnull=True, last_answer_at__lt=now - STALE_START
                ).delete()
            return DuelParticipant.objects.create(duel=duel, user=user, role=role, started_at=now, last_answer_at=now)
    except IntegrityError:
        raise Conflict("duel_taken") from None


def answer(duel: Duel, user, guest_token: str, *, index: int, choice: int, client_ms: int | None) -> dict:
    """One answer. The server clock decides; impossible times and duplicates are rejected."""
    if not 0 <= index < len(duel.words):
        raise ValidationError({"index": "invalid"})
    q = duel.words[index]
    if not 0 <= choice < len(q["options"]):
        raise ValidationError({"choice": "invalid"})
    with transaction.atomic():
        p = participant_for(duel, user, guest_token, lock=True)
        if p is None:
            raise NotFound("not_started")
        if p.finished_at or duel.status in (Duel.COMPLETED, Duel.EXPIRED):
            raise Conflict("already_finished")
        if any(a["index"] == index for a in p.answers):
            raise Conflict("duplicate_answer")
        now = timezone.now()
        ms = int((now - p.last_answer_at).total_seconds() * 1000)
        if ms < MIN_ANSWER_MS or (client_ms is not None and client_ms < MIN_ANSWER_MS):
            raise ValidationError({"detail": "too_fast"})
        correct = choice == q["answer"]
        p.answers = [*p.answers, {"index": index, "choice": choice, "correct": correct, "ms": ms}]
        p.score += int(correct)
        p.time_ms += ms
        p.last_answer_at = now
        p.save(update_fields=["answers", "score", "time_ms", "last_answer_at"])
    return {"index": index, "correct": correct, "correct_index": q["answer"], "answered": len(p.answers)}


def finish(duel: Duel, user, guest_token: str = "") -> DuelParticipant:
    """Close my run. Unanswered questions count as wrong. Idempotent."""
    completed = False
    with transaction.atomic():
        duel = Duel.objects.select_for_update(of=("self",)).select_related("creator").get(pk=duel.pk)
        p = participant_for(duel, user, guest_token, lock=True)
        if p is None:
            raise NotFound("not_started")
        if p.finished_at:
            return p
        if duel.status == Duel.EXPIRED:
            raise Gone("duel_expired")
        now = timezone.now()
        if len(p.answers) < len(duel.words):
            # Giving up early: the waiting time counts too.
            p.time_ms += int((now - p.last_answer_at).total_seconds() * 1000)
        p.finished_at = now
        p.save(update_fields=["time_ms", "finished_at"])
        if p.role == DuelParticipant.CREATOR:
            duel.status = Duel.OPEN
            duel.expires_at = now + LIFETIME
            duel.save(update_fields=["status", "expires_at"])
        else:
            _complete(duel, p, now)
            completed = True
        if p.user_id:
            _record_play(duel, p)
    from . import notify

    if completed:
        notify.opponent_finished(duel)
    elif duel.rematch_of_id:
        notify.rematch_ready(duel)
    return p


# --------------------------------------------------------------------------- result
def compare(a: DuelParticipant, b: DuelParticipant) -> int:
    """1 if a wins, -1 if b wins, 0 = draw. Correct answers first, then the total time."""
    ka, kb = (a.score, -a.time_ms), (b.score, -b.time_ms)
    return (ka > kb) - (ka < kb)


def outcome_of(p: DuelParticipant, other: DuelParticipant) -> str:
    return {1: "win", 0: "draw", -1: "loss"}[compare(p, other)]


def _complete(duel: Duel, opponent: DuelParticipant, now) -> None:
    creator = duel.participants.select_related("user").get(role=DuelParticipant.CREATOR)
    res = compare(creator, opponent)
    duel.status = Duel.COMPLETED
    duel.completed_at = now
    duel.is_draw = res == 0
    duel.winner_id = creator.user_id if res > 0 else opponent.user_id if res < 0 else None
    duel.save(update_fields=["status", "completed_at", "is_draw", "winner"])
    for p, other in ((creator, opponent), (opponent, creator)):
        if p.user_id:
            _reward(p, other)


def _reward(p: DuelParticipant, other: DuelParticipant) -> None:
    from gamification.services import add_xp, grant

    if not DuelParticipant.objects.filter(pk=p.pk, rewarded=False).update(rewarded=True):
        return
    add_xp(p.user, XP[outcome_of(p, other)])
    grant(p.user, "first_duel")
    if Duel.objects.filter(winner_id=p.user_id, status=Duel.COMPLETED).count() >= 10:
        grant(p.user, "duel_wins_10")


def _record_play(duel: Duel, p: DuelParticipant) -> None:
    """Duel words count toward normal learning; the game keeps the streak alive."""
    from gamification.models import GameSession
    from gamification.services import check_achievements, record_activity
    from words.services import apply_answer

    user = p.user
    for a in p.answers:
        item = dict(duel.words[a["index"]]["item"])
        if (item.get("translation_lang") or "uz") != "uz":
            item["translation"] = ""  # UserWord.translation_uz only stores Uzbek
        apply_answer(user, duel.track, item, a["correct"])
    user.refresh_from_db()
    GameSession.objects.create(
        user=user,
        track=duel.track,
        game="duel",
        mode="definition" if duel.mode == "match" else "memorize",
        source=duel.source,
        translation_lang="" if duel.mode == "match" else duel.translation_lang,
        correct=p.score,
        attempts=len(p.answers),
        duration_ms=p.time_ms,
    )
    record_activity(user, 0, p.score, len(p.answers))
    check_achievements(user)


def claim(duel: Duel, user, guest_token: str) -> DuelParticipant:
    """A guest registered / signed in: attach the guest run to the account (once)."""
    with transaction.atomic():
        duel = Duel.objects.select_for_update().get(pk=duel.pk)
        mine = participant_for(duel, user)
        if mine:
            return mine
        p = participant_for(duel, None, guest_token, lock=True)
        if p is None:
            raise NotFound("guest_result_not_found")
        if duel.creator_id == user.pk:
            raise ValidationError({"detail": "own_duel"})
        p.user = user
        p.save(update_fields=["user"])
        if p.finished_at:
            creator = duel.participants.get(role=DuelParticipant.CREATOR)
            if compare(p, creator) > 0:
                duel.winner = user
                duel.save(update_fields=["winner"])
            _reward(p, creator)
            _record_play(duel, p)
    return p


def rematch(duel: Duel, user) -> Duel:
    if duel.status != Duel.COMPLETED or participant_for(duel, user) is None:
        raise ValidationError({"detail": "rematch_not_available"})
    existing = duel.rematches.filter(
        creator=user, status__in=[Duel.PENDING, Duel.OPEN], expires_at__gt=timezone.now()
    ).first()
    if existing:
        return existing
    return create(
        user,
        track=duel.track,
        source=duel.source,
        ref=duel.source_ref,
        mode=duel.mode,
        lang=duel.translation_lang,
        trusted=True,
        rematch_of=duel,
    )


# --------------------------------------------------------------------------- expiry
def expire(duel: Duel) -> bool:
    was_open = duel.status == Duel.OPEN
    updated = Duel.objects.filter(
        pk=duel.pk, status__in=[Duel.PENDING, Duel.OPEN], expires_at__lte=timezone.now()
    ).update(status=Duel.EXPIRED)
    duel.refresh_from_db(fields=["status"])
    if updated and was_open:
        from . import notify

        notify.expired(duel)
    return bool(updated)


def expire_due(limit: int = 30) -> int:
    """Called by the cron endpoints; every creator is notified once."""
    due = Duel.objects.select_related("creator").filter(
        status__in=[Duel.PENDING, Duel.OPEN], expires_at__lte=timezone.now()
    )[:limit]
    return sum(expire(d) for d in due)


# --------------------------------------------------------------------------- referrals / stats
def record_referral(user: User, code: str) -> bool:
    """Set invited_by once. Callers use it only for brand-new accounts that came through a duel link."""
    from accounts.services import record_invite

    duel = Duel.objects.select_related("creator").filter(code=code).first() if code else None
    return record_invite(user, duel.creator if duel else None)


def player(p: DuelParticipant) -> dict:
    u = p.user
    return {"name": u.display_name if u else "", "avatar_url": u.avatar_url if u else "", "is_guest": u is None}


def stats(user) -> dict:
    entries = (
        DuelParticipant.objects.filter(user=user, duel__status=Duel.COMPLETED, finished_at__isnull=False)
        .select_related("duel")
        .prefetch_related("duel__participants__user")
        .order_by("-duel__completed_at")
    )
    out = {"wins": 0, "losses": 0, "draws": 0}
    plural = {"win": "wins", "loss": "losses", "draw": "draws"}
    rivals: dict[int, dict] = {}
    recent = []
    for p in entries:
        other = next((x for x in p.duel.participants.all() if x.pk != p.pk), None)
        if other is None:
            continue
        res = outcome_of(p, other)
        out[plural[res]] += 1
        if other.user_id:
            r = rivals.setdefault(other.user_id, {**player(other), "played": 0, "wins": 0, "losses": 0})
            r["played"] += 1
            r["wins"] += res == "win"
            r["losses"] += res == "loss"
        if len(recent) < 10:
            recent.append(
                {
                    "code": p.duel.code,
                    "mode": p.duel.mode,
                    "track": p.duel.track,
                    "outcome": res,
                    "my_score": p.score,
                    "other_score": other.score,
                    "total": len(p.duel.words),
                    "other": player(other),
                    "completed_at": p.duel.completed_at,
                }
            )
    waiting = Duel.objects.filter(
        creator=user, status__in=[Duel.PENDING, Duel.OPEN], expires_at__gt=timezone.now()
    ).defer("words")[:10]
    return {
        **out,
        "recent": recent,
        "rivals": sorted(rivals.values(), key=lambda r: (-r["played"], -r["wins"]))[:5],
        "open": [
            {
                "code": d.code,
                "mode": d.mode,
                "track": d.track,
                "status": d.status,
                "source_label": d.source_label,
                "expires_at": d.expires_at,
            }
            for d in waiting
        ],
        "invited": User.objects.filter(invited_by=user).count(),
    }
