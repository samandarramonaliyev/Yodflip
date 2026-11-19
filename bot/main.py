"""Yodflip Telegram bot (aiogram 3).

Commands: /start /daily /stats /review /remind HH:MM|off
Talks to the backend's internal bot API (X-Bot-Secret).

Modes
* webhook (production): when WEBHOOK_BASE_URL (or Render's RENDER_EXTERNAL_URL) is set, an aiohttp
  server listens on $PORT, registers the webhook with Telegram on startup (with a secret token)
  and serves GET /health. Daily reminders run in the same process.
* polling (local): when no public URL is configured.
Without TELEGRAM_BOT_TOKEN the bot exits cleanly (the rest of the stack runs without it).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sys

import httpx
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from texts import t

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("yodflip.bot")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


TOKEN = env("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = env("WEBAPP_URL").rstrip("/")  # public HTTPS URL of the Mini App (the web service)
API_URL = env("BOT_BACKEND_URL", WEBAPP_URL).rstrip("/")  # backend base URL (same as the web app by default)
SECRET = env("BOT_API_SECRET")
WEBHOOK_BASE_URL = (env("WEBHOOK_BASE_URL") or env("RENDER_EXTERNAL_URL")).rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
PORT = int(env("PORT", "8080"))
REMINDER_INTERVAL = int(env("REMINDER_INTERVAL_SECONDS", "60"))


def webhook_secret_token(seed: str) -> str:
    """Telegram allows only [A-Za-z0-9_-] in secret_token, so derive a hex token from any secret."""
    return hashlib.sha256(f"yodflip-webhook:{seed}".encode()).hexdigest()


dp = Dispatcher()


def lang_of(message: Message, stats: dict | None = None) -> str:
    if stats and stats.get("ui_language"):
        return stats["ui_language"]
    code = (message.from_user.language_code or "") if message.from_user else ""
    return "ru" if code.startswith("ru") else "en" if code.startswith("en") else "uz"


def open_button(text: str, path: str = "/") -> InlineKeyboardMarkup:
    url = f"{WEBAPP_URL}{path}"
    # Telegram only accepts HTTPS for Web App buttons; fall back to a plain link in local dev.
    if url.startswith("https://"):
        btn = InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
    else:
        btn = InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


async def api_get(path: str) -> dict | list | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{API_URL}/api/games/bot/{path}", headers={"X-Bot-Secret": SECRET})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        log.warning("Backend call failed: %s", exc)
        return None


async def api_post(path: str, data: dict) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{API_URL}/api/games/bot/{path}", json=data, headers={"X-Bot-Secret": SECRET})
            return r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Backend call failed: %s", exc)
        return None


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    lang = lang_of(message)
    name = message.from_user.first_name if message.from_user else ""
    await message.answer(t(lang, "welcome", name=name), reply_markup=open_button(t(lang, "open"), "/"))


@dp.message(Command("daily"))
async def cmd_daily(message: Message) -> None:
    lang = lang_of(message)
    data = await api_get("daily/")
    if not data:
        await message.answer(t(lang, "error"))
        return
    lines = [t(lang, "daily_title")]
    for track, flag in (("en", "EN ·"), ("de", "DE ·")):
        words = ", ".join(w["term"] for w in data.get(track, []))
        lines.append(f"\n{flag} {words}")
    await message.answer("\n".join(lines), reply_markup=open_button(t(lang, "play_daily"), "/play/daily"))


@dp.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    stats = await api_get(f"stats/{message.from_user.id}/")
    lang = lang_of(message, stats if isinstance(stats, dict) else None)
    if not stats or not stats.get("registered"):
        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
        return
    en, de = stats["tracks"]["en"], stats["tracks"]["de"]
    await message.answer(
        t(
            lang,
            "stats",
            level=stats["level"],
            xp=stats["xp"],
            streak=stats["streak"],
            en_learned=en["learned"],
            en_total=en["total"],
            de_learned=de["learned"],
            de_total=de["total"],
            today="✅" if stats["played_today"] else "⏳",
        ),
        reply_markup=open_button(t(lang, "open"), "/profile"),
    )


@dp.message(Command("review"))
async def cmd_review(message: Message) -> None:
    stats = await api_get(f"stats/{message.from_user.id}/")
    lang = lang_of(message, stats if isinstance(stats, dict) else None)
    if not stats or not stats.get("registered"):
        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
        return
    en, de = stats["tracks"]["en"]["due"], stats["tracks"]["de"]["due"]
    text = t(lang, "review", en=en, de=de) if en or de else t(lang, "review_none")
    await message.answer(text, reply_markup=open_button(t(lang, "play_review"), "/play/review"))


@dp.message(Command("remind"))
async def cmd_remind(message: Message, command: CommandObject) -> None:
    lang = lang_of(message)
    arg = (command.args or "").strip().lower()
    if not arg:
        await message.answer(t(lang, "remind_help"))
        return
    if arg != "off" and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", arg):
        await message.answer(t(lang, "remind_help"))
        return
    value = "off" if arg == "off" else f"{int(arg.split(':')[0]):02d}:{arg.split(':')[1]}"
    res = await api_post(f"reminder/{message.from_user.id}/", {"reminder_time": value})
    if not res or not res.get("ok"):
        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
        return
    await message.answer(t(lang, "remind_off") if value == "off" else t(lang, "remind_set", time=value))


async def reminder_loop(bot: Bot) -> None:
    """Every minute: remind users whose reminder time passed and who haven't played today."""
    while True:
        await asyncio.sleep(REMINDER_INTERVAL)
        users = await api_get("reminders-due/?mark=1")
        for u in users or []:
            lang = u.get("ui_language", "uz")
            try:
                await bot.send_message(
                    u["telegram_id"],
                    t(lang, "reminder", streak=u.get("streak", 0), due=u.get("due", 0)),
                    reply_markup=open_button(t(lang, "open"), "/"),
                )
            except Exception as exc:  # noqa: BLE001 - user may have blocked the bot
                log.info("Reminder to %s failed: %s", u.get("telegram_id"), exc)


COMMANDS = [
    BotCommand(command="start", description="Open Yodflip"),
    BotCommand(command="daily", description="Today's challenge"),
    BotCommand(command="stats", description="My progress"),
    BotCommand(command="review", description="Words due for review"),
    BotCommand(command="remind", description="Daily reminder: /remind 19:00 or off"),
]


async def configure_bot(bot: Bot) -> None:
    await bot.set_my_commands(COMMANDS)
    if WEBAPP_URL.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Play", web_app=WebAppInfo(url=WEBAPP_URL)))
    else:
        log.warning("WEBAPP_URL is not an https:// URL (%r): Mini App buttons fall back to plain links.", WEBAPP_URL)


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "mode": "webhook"})


def build_webhook_app(bot: Bot, dispatcher: Dispatcher, secret_token: str) -> web.Application:
    """aiohttp app: POST /telegram/webhook (secret-checked by aiogram), GET /health and GET /."""
    app = web.Application()
    SimpleRequestHandler(dispatcher=dispatcher, bot=bot, secret_token=secret_token).register(app, path=WEBHOOK_PATH)
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    setup_application(app, dispatcher, bot=bot)
    return app


async def run_webhook(bot: Bot) -> None:
    secret_token = webhook_secret_token(env("WEBHOOK_SECRET") or TOKEN)
    url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

    async def on_startup(_app: web.Application) -> None:
        await configure_bot(bot)
        await bot.set_webhook(url, secret_token=secret_token, allowed_updates=dp.resolve_used_update_types())
        log.info("Webhook set to %s", url)
        _app["reminders"] = asyncio.create_task(reminder_loop(bot))

    async def on_cleanup(_app: web.Application) -> None:
        task = _app.get("reminders")
        if task:
            task.cancel()

    app = build_webhook_app(bot, dp, secret_token)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Webhook server listening on :%s", PORT)
    await asyncio.Event().wait()


async def run_polling(bot: Bot) -> None:
    await configure_bot(bot)
    await bot.delete_webhook(drop_pending_updates=False)
    asyncio.create_task(reminder_loop(bot))
    log.info("Polling mode (no WEBHOOK_BASE_URL / RENDER_EXTERNAL_URL).")
    await dp.start_polling(bot)


async def main() -> None:
    if not TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN is not set: bot skipped.")
        return
    if not API_URL or not SECRET:
        log.error("BOT_BACKEND_URL/WEBAPP_URL and BOT_API_SECRET must be set.")
        sys.exit(1)
    bot = Bot(TOKEN)
    if WEBHOOK_BASE_URL:
        await run_webhook(bot)
    else:
        await run_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
