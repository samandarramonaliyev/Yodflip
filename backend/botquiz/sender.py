"""Quiz sending: small pace (≤25 messages / s), 429 retries, 403 → inactive, bounded run time."""

from __future__ import annotations

import asyncio
import logging
import time

from asgiref.sync import async_to_sync, sync_to_async

from telegram_bot import delivery

from . import services

log = logging.getLogger(__name__)
PACE = delivery.PACE
BUDGET = 24  # seconds; cron-job.org stops waiting after 30


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _send_one(bot, job: dict, deadline: float, stats: dict) -> str:
    from telegram_bot.quiz_handlers import invite_markup
    from telegram_bot.texts import t

    text = t(job["lang"], "quiz_invite", n=job["count"])
    markup = invite_markup(job["lang"], job["sid"])

    async def send():
        return await bot.send_message(
            job["chat_id"], text, reply_markup=markup, request_timeout=delivery.REQUEST_TIMEOUT
        )

    out = await delivery.deliver(send, sleep, deadline)
    if out.status != delivery.SENT:
        log.warning("Quiz to user %s: %s (%s)", job["user_id"], out.status, out.detail)
        delivery.count_error(stats, out.detail)
    if out.status == delivery.BLOCKED:
        await sync_to_async(services.mark_blocked)(job["user_id"])
    if out.status in (delivery.BLOCKED, delivery.REJECTED):  # the plain reminder may still go out today
        await sync_to_async(services.not_delivered)(job["settings_id"])
    elif out.status in (delivery.RETRY_LATER, delivery.FATAL):
        await sync_to_async(services.release)(job)
    return out.status


async def _run(due: list, budget: float, stats: dict) -> None:
    from telegram_bot.bot import make_bot

    deadline = time.monotonic() + budget
    bot = make_bot()
    try:
        for n, (settings_id, day) in enumerate(due):
            if time.monotonic() > deadline:
                stats["remaining"] = len(due) - n
                break
            try:
                job = await sync_to_async(services.claim)(settings_id, day)
            except Exception as exc:  # one broken user must not stop everybody else
                log.exception("Quiz for settings %s could not be built", settings_id)
                stats["failed"] += 1
                delivery.count_error(stats, delivery.error_text(exc))
                continue
            if job is None:
                key = "claimed_elsewhere_or_no_words"
                stats["skipped"][key] = stats["skipped"].get(key, 0) + 1
                continue
            status = await _send_one(bot, job, deadline, stats)
            stats[delivery.STAT_KEY[status]] += 1
            if status == delivery.FATAL:
                stats["remaining"] = len(due) - n - 1
                break
            await sleep(PACE)
    finally:
        await bot.session.close()


def send_due_quizzes(budget: float = BUDGET) -> dict:
    services.cleanup()
    due, skipped = services.select_due()
    stats = delivery.new_stats(len(due), skipped)
    if due:
        async_to_sync(_run)(due, budget, stats)
    return stats
