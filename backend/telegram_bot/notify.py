"""Send many one-off notifications (class deadlines, league results) with one claim per message.

Each note is claimed (a sync callable that returns True exactly once, e.g. a conditional UPDATE or a
unique row) right before it is sent, so overlapping or repeated cron calls never send twice. A claim
is given back only when Telegram certainly did not deliver (429 that can't be waited out, no
connection, wrong token), the same rule as the reminders and the quiz.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import NamedTuple

from asgiref.sync import async_to_sync, sync_to_async

from . import delivery

log = logging.getLogger(__name__)


class Note(NamedTuple):
    user_id: int
    chat_id: int
    text: str
    button: str
    path: str
    claim: Callable[[], bool]
    release: Callable[[], None] | None = None


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _run(notes: list[Note], deadline: float, stats: dict) -> None:
    from botquiz import services as quiz

    from .bot import make_bot
    from .handlers import open_button

    bot = make_bot()
    try:
        for n, note in enumerate(notes):
            if time.monotonic() > deadline:
                stats["remaining"] = len(notes) - n
                break
            try:
                won = await sync_to_async(note.claim)()
            except Exception as exc:  # one broken row must not stop the others
                log.exception("Notification for user %s could not be claimed", note.user_id)
                stats["failed"] += 1
                delivery.count_error(stats, delivery.error_text(exc))
                continue
            if not won:
                stats["skipped"]["claimed_elsewhere"] = stats["skipped"].get("claimed_elsewhere", 0) + 1
                continue
            markup = open_button(note.button, note.path) if note.button else None

            async def send(note=note, markup=markup):
                return await bot.send_message(
                    note.chat_id, note.text, reply_markup=markup, request_timeout=delivery.REQUEST_TIMEOUT
                )

            out = await delivery.deliver(send, sleep, deadline)
            if out.status != delivery.SENT:
                log.warning("Notification to user %s: %s (%s)", note.user_id, out.status, out.detail)
                delivery.count_error(stats, out.detail)
            if out.status == delivery.BLOCKED:
                await sync_to_async(quiz.mark_blocked)(note.user_id)
            elif out.status in (delivery.RETRY_LATER, delivery.FATAL) and note.release:
                await sync_to_async(note.release)()
            stats[delivery.STAT_KEY[out.status]] += 1
            if out.status == delivery.FATAL:
                stats["remaining"] = len(notes) - n - 1
                break
            await sleep(delivery.PACE)
    finally:
        await bot.session.close()


def send_notes(notes: list[Note], budget: float, skipped: dict | None = None) -> dict:
    stats = delivery.new_stats(len(notes), dict(skipped or {}))
    if notes:
        async_to_sync(_run)(notes, time.monotonic() + budget, stats)
    return stats
