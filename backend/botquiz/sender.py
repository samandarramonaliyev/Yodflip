"""Hourly sending: small pace (≤25 messages / s), 429 retries, 403 → inactive, bounded run time."""

from __future__ import annotations

import asyncio
import logging
import time

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from asgiref.sync import async_to_sync, sync_to_async

from . import services

log = logging.getLogger(__name__)
PACE = 1 / 25
BUDGET = 24  # seconds; cron-job.org stops waiting after 30
MAX_RETRIES = 3


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _send_one(bot, job: dict, deadline: float) -> str:
    from telegram_bot.quiz_handlers import invite_markup
    from telegram_bot.texts import t

    text = t(job["lang"], "quiz_invite", n=job["count"])
    for _ in range(MAX_RETRIES + 1):
        try:
            await bot.send_message(job["chat_id"], text, reply_markup=invite_markup(job["lang"], job["sid"]))
            return "sent"
        except TelegramRetryAfter as exc:
            if time.monotonic() + exc.retry_after > deadline:
                break
            await sleep(exc.retry_after)
        except TelegramForbiddenError:
            await sync_to_async(services.mark_blocked)(job["user_id"])
            return "blocked"
        except Exception as exc:  # noqa: BLE001 - maybe delivered: never send a second one today
            log.info("Quiz to user %s failed: %s", job["user_id"], exc)
            return "failed"
    await sync_to_async(services.release)(job)
    return "retry_later"


async def _run(due: list, budget: float) -> dict:
    from telegram_bot.bot import make_bot

    stats = {"due": len(due), "sent": 0, "blocked": 0, "failed": 0, "retry_later": 0, "skipped": 0, "remaining": 0}
    deadline = time.monotonic() + budget
    bot = make_bot()
    try:
        for n, (settings_id, day) in enumerate(due):
            if time.monotonic() > deadline:
                stats["remaining"] = len(due) - n
                break
            job = await sync_to_async(services.claim)(settings_id, day)
            if job is None:
                stats["skipped"] += 1
                continue
            stats[await _send_one(bot, job, deadline)] += 1
            await sleep(PACE)
    finally:
        await bot.session.close()
    return stats


def send_due_quizzes(budget: float = BUDGET) -> dict:
    services.cleanup()
    due = services.due_settings()
    return async_to_sync(_run)(due, budget) if due else {"due": 0, "sent": 0}
