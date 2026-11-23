"""Synchronous data access used by the bot handlers (plain Django ORM)."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from accounts.models import User
from games.sources import daily_words
from gamification.services import level_for_xp, today
from words.services import due_queryset


def webhook_secret() -> str:
    """Secret used in the webhook path and as Telegram's secret_token ([A-Za-z0-9_-] only)."""
    seed = settings.TELEGRAM_WEBHOOK_SECRET or f"{settings.SECRET_KEY}:{settings.TELEGRAM_BOT_TOKEN}"
    return hashlib.sha256(f"yodflip-webhook:{seed}".encode()).hexdigest()


def _derived_cron_secret(seed: str) -> str:
    return hashlib.sha256(f"yodflip-cron:{seed}".encode()).hexdigest()[:40]


def cron_secret() -> str:
    """The secret to put in /bot/cron/<secret>/.

    If BOT_CRON_SECRET is set, the URL secret IS that value (whitespace stripped).
    Otherwise a value derived from SECRET_KEY is used.
    """
    raw = (settings.BOT_CRON_SECRET or "").strip()
    return raw or _derived_cron_secret(f"{settings.SECRET_KEY}:cron")


def accepted_cron_secrets() -> list[str]:
    """All secrets the cron URL accepts. Besides cron_secret(), the older derived form
    sha256("yodflip-cron:" + BOT_CRON_SECRET)[:40] keeps working, so links set up earlier don't break."""
    raw = (settings.BOT_CRON_SECRET or "").strip()
    secrets = [cron_secret()]
    if raw:
        secrets.append(_derived_cron_secret(raw))
    return secrets


def cron_secret_matches(given: str) -> bool:
    given = (given or "").strip().strip("/")
    if not given:
        return False
    # Compare against every accepted value (no early exit, constant-time per comparison).
    results = [hmac.compare_digest(given.encode(), s.encode()) for s in accepted_cron_secrets()]
    return any(results)


def webapp_url(path: str = "/") -> str:
    return f"{settings.PUBLIC_URL.rstrip('/')}{path}" if settings.PUBLIC_URL else ""


def user_language(tg_id: int, fallback_code: str = "") -> str:
    u = User.objects.filter(telegram_id=tg_id).only("ui_language").first()
    if u:
        return u.ui_language
    return "ru" if fallback_code.startswith("ru") else "en" if fallback_code.startswith("en") else "uz"


def stats(tg_id: int) -> dict:
    u = User.objects.filter(telegram_id=tg_id).first()
    if not u:
        return {"registered": False}
    out = {
        "registered": True,
        "ui_language": u.ui_language,
        "xp": u.xp,
        "level": level_for_xp(u.xp),
        "streak": u.streak,
        "played_today": u.last_active_date == today(),
        "tracks": {},
    }
    for track in ("en", "de"):
        qs = u.words.filter(track=track)
        out["tracks"][track] = {
            "learned": qs.filter(box__gte=5).count(),
            "total": qs.filter(seen=True).count(),
            "due": due_queryset(u, track).count(),
        }
    return out


def daily() -> dict[str, list[str]]:
    return {track: [w.display for w in daily_words(track, today())] for track in ("en", "de")}


def set_reminder(tg_id: int, value: str) -> str | None:
    """value = 'HH:MM' or 'off'. Returns the stored value ('off' / 'HH:MM') or None if not registered."""
    u = User.objects.filter(telegram_id=tg_id).first()
    if not u:
        return None
    u.reminder_time = None if value == "off" else datetime.strptime(value, "%H:%M").time()
    u.save(update_fields=["reminder_time"])
    return "off" if u.reminder_time is None else u.reminder_time.strftime("%H:%M")


def take_due_reminders(limit: int = 500) -> list[dict]:
    """Users whose reminder time has passed today, who haven't played and weren't reminded.

    Marks them as reminded (so each user gets at most one reminder per day).
    """
    now = timezone.localtime()
    day = now.date()
    users = list(
        User.objects.filter(telegram_id__isnull=False, reminder_time__isnull=False, reminder_time__lte=now.time())
        .exclude(last_active_date=day)
        .exclude(last_reminder_date=day)
        .exclude(quiz_settings__last_sent_at__date=day)  # the quiz already reminded them
        .exclude(quiz_settings__bot_blocked=True)[:limit]
    )
    User.objects.filter(pk__in=[u.pk for u in users]).update(last_reminder_date=day)
    return [
        {
            "telegram_id": u.telegram_id,
            "ui_language": u.ui_language,
            "streak": u.streak,
            "due": due_queryset(u, u.active_track).count(),
        }
        for u in users
    ]
