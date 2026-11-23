"""Quiz sessions, settings and the hourly schedule (plain Django ORM)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones

from django.db import transaction
from django.utils import timezone

from accounts.models import TranslationPreference, User
from games.scoring import session_xp
from gamification.models import GameSession
from gamification.services import check_achievements, record_activity, today
from words.services import apply_answer
from words.translations import allowed_translation_langs

from .models import DEFAULT_TZ, QUESTION_CHOICES, QuizSession, QuizSettings
from .selection import build_questions

EXPIRES = timedelta(hours=24)
MORE = 5


def settings_for(user: User) -> QuizSettings:
    return QuizSettings.objects.get_or_create(user=user)[0]


def valid_timezone(name: str) -> bool:
    return name in available_timezones()


def quiz_lang(user: User, track: str, conf: QuizSettings) -> str:
    """Language of the quiz: its own setting, else the app's preferred translation language."""
    allowed = allowed_translation_langs(track)
    if conf.translation_lang in allowed:
        return conf.translation_lang
    pref = TranslationPreference.objects.filter(user=user, track=track).first()
    return pref.preferred_translation_lang if pref and pref.preferred_translation_lang in allowed else "uz"


# --------------------------------------------------------------------------- sessions
def new_session(user: User, count: int | None = None) -> QuizSession | None:
    """None when there is nothing to ask."""
    conf = settings_for(user)
    track = user.active_track
    lang = quiz_lang(user, track, conf)
    questions = build_questions(user, track, lang, count or conf.questions)
    if not questions:
        return None
    return QuizSession.objects.create(user=user, track=track, translation_lang=lang, questions=questions)


def user_by_tg(tg_id: int) -> User | None:
    return User.objects.filter(telegram_id=tg_id, is_active=True).first()


def mark_reachable(tg_id: int) -> None:
    """The user wrote to the bot: it isn't blocked any more."""
    QuizSettings.objects.filter(user__telegram_id=tg_id, bot_blocked=True).update(bot_blocked=False)


def mark_blocked(user_id: int) -> None:
    QuizSettings.objects.filter(user_id=user_id).update(bot_blocked=True)


def _alive(s: QuizSession | None) -> bool:
    return s is not None and s.status != QuizSession.DONE and s.created_at > timezone.now() - EXPIRES


def begin(tg_id: int, sid: str) -> QuizSession | None:
    """Pressing "Boshlash" (again): the session at its current question, None when stale."""
    s = QuizSession.objects.filter(sid=sid, user__telegram_id=tg_id).first()
    if not _alive(s):
        return None
    if s.status == QuizSession.NEW:
        s.status, s.started_at = QuizSession.ACTIVE, timezone.now()
        s.save(update_fields=["status", "started_at"])
    return s


def answer(tg_id: int, sid: str, index: int, choice: int) -> dict:
    """{"stale": "expired" | "answered"} or the checked question + the session's new state."""
    with transaction.atomic():
        s = QuizSession.objects.select_for_update().filter(sid=sid, user__telegram_id=tg_id).first()
        if not _alive(s):
            return {"stale": "expired"}
        if index != s.index or index >= len(s.questions):
            return {"stale": "answered"}  # pressed twice / an older question
        q = s.questions[index]
        if not 0 <= choice < len(q["options"]):
            return {"stale": "answered"}
        correct = choice == q["answer"]
        user = s.user
        apply_answer(user, s.track, q["item"], correct)
        s.index += 1
        s.correct += int(correct)
        s.status = QuizSession.ACTIVE
        result = {"question": q, "choice": choice, "correct": correct, "session": s}
        if s.index >= len(s.questions):
            result["summary"] = _finish(s)
        s.save()
    return result


def _finish(s: QuizSession) -> dict:
    """The quiz counts as a game of today: XP, streak, activity, badges (exactly once)."""
    user = s.user
    user.refresh_from_db()
    s.status, s.finished_at = QuizSession.DONE, timezone.now()
    total = len(s.questions)
    xp, perfect = session_xp("review", s.correct, total)
    ms = int((s.finished_at - (s.started_at or s.created_at)).total_seconds() * 1000)
    GameSession.objects.create(
        user=user,
        track=s.track,
        game="review",
        mode="memorize",
        source="bot_quiz",
        translation_lang=s.translation_lang,
        xp=xp,
        correct=s.correct,
        attempts=total,
        duration_ms=ms,
    )
    record_activity(user, xp, s.correct, total)
    check_achievements(user, perfect=perfect)
    return {"correct": s.correct, "total": total, "xp": xp, "streak": user.streak}


# --------------------------------------------------------------------------- settings
def update_settings(user: User, **patch) -> QuizSettings:
    conf = settings_for(user)
    for k, v in patch.items():
        setattr(conf, k, v)
    if patch:
        conf.save(update_fields=list(patch))
    return conf


def settings_dict(conf: QuizSettings) -> dict:
    return {
        "enabled": conf.enabled,
        "hour": conf.hour,
        "timezone": conf.timezone,
        "questions": conf.questions,
        "translation_lang": conf.translation_lang,
        "quiet_days": conf.quiet_days,
        "bot_blocked": conf.bot_blocked,
    }


def menu_action(user: User, action: str, value: str) -> QuizSettings:
    """Buttons of the bot's settings menu."""
    conf = settings_for(user)
    if action == "on":
        conf.enabled = not conf.enabled
    elif action == "h" and value in ("+", "-"):
        conf.hour = (conf.hour + (1 if value == "+" else -1)) % 24
    elif action == "n" and value.isdigit() and int(value) in QUESTION_CHOICES:
        conf.questions = int(value)
    elif action == "l" and value in ("uz", "ru", "en", "de"):
        conf.translation_lang = value
    elif action == "d" and value.isdigit() and int(value) < 7:
        conf.quiet_days = sorted(set(conf.quiet_days) ^ {int(value)})
    conf.save()
    return conf


# --------------------------------------------------------------------------- schedule
def due_settings(now: datetime | None = None, limit: int = 1000) -> list[tuple[int, object]]:
    """[(settings id, the user's local date)] of users whose chosen hour is now in their timezone."""
    now = now or timezone.now()
    missing = User.objects.filter(telegram_id__isnull=False, quiz_settings__isnull=True).values_list("id", flat=True)
    QuizSettings.objects.bulk_create([QuizSettings(user_id=i) for i in missing], ignore_conflicts=True)
    out: list[tuple[int, object]] = []
    for tz in QuizSettings.objects.order_by().values_list("timezone", flat=True).distinct():
        local = now.astimezone(ZoneInfo(tz if valid_timezone(tz) else DEFAULT_TZ))
        rows = (
            QuizSettings.objects.filter(
                enabled=True,
                bot_blocked=False,
                timezone=tz,
                hour=local.hour,
                user__telegram_id__isnull=False,
                user__is_active=True,
            )
            .exclude(last_sent_on=local.date())
            .exclude(user__last_active_date=today())
            .order_by("id")[:limit]
        )
        out += [(c.id, local.date()) for c in rows if local.weekday() not in c.quiet_days]
    return out[:limit]


def claim(settings_id: int, day) -> dict | None:
    """Reserve today's quiz for one user (atomic, so overlapping cron calls never send twice)."""
    now = timezone.now()
    updated = (
        QuizSettings.objects.filter(pk=settings_id, enabled=True)
        .exclude(last_sent_on=day)
        .update(last_sent_on=day, last_sent_at=now)
    )
    if not updated:
        return None
    user = User.objects.get(quiz_settings__pk=settings_id)
    session = new_session(user)
    if session is None:
        return None
    return {
        "settings_id": settings_id,
        "user_id": user.pk,
        "chat_id": user.telegram_id,
        "lang": user.ui_language,
        "sid": session.sid,
        "count": len(session.questions),
    }


def release(job: dict) -> None:
    """Telegram refused the message (429): nothing was delivered, so it may be sent later today."""
    QuizSettings.objects.filter(pk=job["settings_id"]).update(last_sent_on=None, last_sent_at=None)
    QuizSession.objects.filter(sid=job["sid"]).delete()


def cleanup() -> None:
    QuizSession.objects.filter(created_at__lt=timezone.now() - timedelta(days=7)).delete()
