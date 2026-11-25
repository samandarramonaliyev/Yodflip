"""Running aiogram inside Django (webhook mode, no separate process).

Each webhook request runs the async dispatcher via asgiref's `async_to_sync` in the (sync)
gunicorn worker: a short-lived Bot session is opened, the update is dispatched to the handlers
and the session is closed. Handlers reach the ORM through `sync_to_async` (thread-sensitive),
which runs those calls back on the request's own thread and database connection.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from asgiref.sync import async_to_sync
from django.conf import settings

from .handlers import open_button, router
from .quiz_handlers import router as quiz_router

dispatcher = Dispatcher()
dispatcher.include_router(quiz_router)
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


async def _send_to_user(chat_id: int, text: str, button: str, path: str) -> None:
    bot = make_bot()
    try:
        await bot.send_message(chat_id, text, reply_markup=open_button(button, path), request_timeout=8)
    finally:
        await bot.session.close()


def send_to_user(chat_id: int, text: str, button: str, path: str) -> None:
    """One message with a Web App button (duel notifications)."""
    async_to_sync(_send_to_user)(chat_id, text, button, path)
