"""Daily text reminder: who is due, one claim per user and local day, sending."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from asgiref.sync import async_to_sync, sync_to_async
from django.utils import timezone

from accounts.models import User
from botquiz import services as quiz
from botquiz.models import DEFAULT_TZ
from gamification.services import today
from words.services import due_queryset

from . import delivery

log = logging.getLogger(__name__)
BUDGET = 24


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def local_now(user: User, now: datetime) -> datetime:
    tz = user.quiz_settings.timezone if hasattr(user, "quiz_settings") else DEFAULT_TZ
    return now.astimezone(ZoneInfo(tz if quiz.valid_timezone(tz) else DEFAULT_TZ))


def skip_reason(user: User, now: datetime) -> str | None:
    """None = the reminder is due now."""
    local = local_now(user, now)
    conf = getattr(user, "quiz_settings", None)
    if not user.is_active:
        return "inactive_account"
    if user.reminder_time is None:
        return "reminder_off"
    if conf and conf.bot_blocked:
        return "bot_blocked"
    if user.reminder_time > local.time():
        return "not_yet_time"
    if user.last_active_date == today():
        return "played_today"
    if user.last_reminder_date == local.date():
        return "already_sent_today"
    if conf and conf.last_sent_at and conf.last_sent_at.astimezone(local.tzinfo).date() == local.date():
        return "quiz_sent_today"
    return None


def select_due(now: datetime | None = None) -> tuple[list[User], dict[str, int]]:
    """(due users, {reason: number of skipped users}) over everyone with Telegram."""
    now = now or timezone.now()
    due, skipped = [], Counter()
    for user in User.objects.filter(telegram_id__isnull=False).select_related("quiz_settings").order_by("id"):
        reason = skip_reason(user, now)
        if reason:
            skipped[reason] += 1
        else:
            due.append(user)
    return due, dict(skipped)


def claim(user: User, day) -> bool:
    """Atomic: overlapping runs never remind a user twice; a user who just played is left alone."""
    qs = User.objects.filter(pk=user.pk, reminder_time__isnull=False)
    return bool(qs.exclude(last_reminder_date=day).exclude(last_active_date=today()).update(last_reminder_date=day))


def release(user: User) -> None:
    User.objects.filter(pk=user.pk).update(last_reminder_date=user.last_reminder_date)


def _prepare(user: User) -> int | None:
    """The user's due words, or None when the claim failed."""
    words = due_queryset(user, user.active_track).count()
    return words if claim(user, local_now(user, timezone.now()).date()) else None


async def _run(users: list[User], deadline: float, stats: dict) -> None:
    from .bot import make_bot
    from .handlers import open_button
    from .texts import t

    bot = make_bot()
    try:
        for n, user in enumerate(users):
            if time.monotonic() > deadline:
                stats["remaining"] = len(users) - n
                break
            try:
                words = await sync_to_async(_prepare)(user)
            except Exception as exc:  # one broken user must not stop everybody else
                log.exception("Reminder for user %s could not be prepared", user.pk)
                stats["failed"] += 1
                delivery.count_error(stats, delivery.error_text(exc))
                continue
            if words is None:
                stats["skipped"]["claimed_elsewhere"] = stats["skipped"].get("claimed_elsewhere", 0) + 1
                continue
            lang = user.ui_language
            text = t(lang, "reminder", streak=user.streak, due=words)
            markup = open_button(t(lang, "open"), "/")

            async def send(chat_id=user.telegram_id, text=text, markup=markup):
                return await bot.send_message(
                    chat_id, text, reply_markup=markup, request_timeout=delivery.REQUEST_TIMEOUT
                )

            out = await delivery.deliver(send, sleep, deadline)
            if out.status != delivery.SENT:
                log.warning("Reminder to user %s: %s (%s)", user.pk, out.status, out.detail)
                delivery.count_error(stats, out.detail)
            if out.status == delivery.BLOCKED:
                await sync_to_async(quiz.mark_blocked)(user.pk)
            elif out.status in (delivery.RETRY_LATER, delivery.FATAL):
                await sync_to_async(release)(user)
            stats[delivery.STAT_KEY[out.status]] += 1
            if out.status == delivery.FATAL:
                stats["remaining"] = len(users) - n - 1
                break
            await sleep(delivery.PACE)
    finally:
        await bot.session.close()


def send_due_reminders(budget: float = BUDGET) -> dict:
    due, skipped = select_due()
    stats = delivery.new_stats(len(due), skipped)
    if due:
        async_to_sync(_run)(due, time.monotonic() + budget, stats)
    return stats
