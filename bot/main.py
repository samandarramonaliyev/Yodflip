"""Yodflip Telegram bot (aiogram 3).

Commands: /start /daily /stats /review /remind HH:MM|off
Talks to the backend's internal bot API (X-Bot-Secret). Without TELEGRAM_BOT_TOKEN it exits
cleanly (MOCK mode: the rest of the stack runs without a bot).
"""

from __future__ import annotations

import asyncio
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

from texts import t

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wordflip.bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
WEBAPP_URL = os.environ.get("WEBAPP_URL", os.environ.get("FRONTEND_URL", "http://localhost:5173")).rstrip("/")
API_URL = os.environ.get("BOT_BACKEND_URL", "http://localhost:8000").rstrip("/")
SECRET = os.environ.get("BOT_API_SECRET", "dev-bot-secret")
REMINDER_INTERVAL = int(os.environ.get("REMINDER_INTERVAL_SECONDS", "60"))

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


async def main() -> None:
    if not TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN is not set: bot skipped (MOCK mode).")
        return
    bot = Bot(TOKEN)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Open Yodflip"),
            BotCommand(command="daily", description="Today's challenge"),
            BotCommand(command="stats", description="My progress"),
            BotCommand(command="review", description="Words due for review"),
            BotCommand(command="remind", description="Daily reminder: /remind 19:00 or off"),
        ]
    )
    if WEBAPP_URL.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Play", web_app=WebAppInfo(url=WEBAPP_URL)))
    asyncio.create_task(reminder_loop(bot))
    log.info("Bot started. Web App URL: %s", WEBAPP_URL)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
