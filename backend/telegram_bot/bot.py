"""Running aiogram inside Django (webhook mode, no separate process).

Each webhook request runs the async dispatcher via asgiref's `async_to_sync` in the (sync)
gunicorn worker: a short-lived Bot session is opened, the update is dispatched to the handlers
and the session is closed. Handlers reach the ORM through `sync_to_async` (thread-sensitive),
which runs those calls back on the request's own thread and database connection.
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from asgiref.sync import async_to_sync
from django.conf import settings

from .handlers import open_button, router
from .texts import t

log = logging.getLogger(__name__)

dispatcher = Dispatcher()
dispatcher.include_router(router)


def make_bot() -> Bot:
    return Bot(settings.TELEGRAM_BOT_TOKEN)


async def _process(update: dict) -> None:
    bot = make_bot()
    try:
        await dispatcher.feed_raw_update(bot, update)
    finally:
        await bot.session.close()


def process_update(update: dict) -> None:
    async_to_sync(_process)(update)


async def _send_reminders(users: list[dict]) -> int:
    bot = make_bot()
    sent = 0
    try:
        for u in users:
            lang = u.get("ui_language", "uz")
            try:
                await bot.send_message(
                    u["telegram_id"],
                    t(lang, "reminder", streak=u.get("streak", 0), due=u.get("due", 0)),
                    reply_markup=open_button(t(lang, "open"), "/"),
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001 - e.g. the user blocked the bot
                log.info("Reminder to %s failed: %s", u.get("telegram_id"), exc)
    finally:
        await bot.session.close()
    return sent


def send_reminders(users: list[dict]) -> int:
    return async_to_sync(_send_reminders)(users) if users else 0
