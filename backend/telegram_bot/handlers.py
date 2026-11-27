"""aiogram 3 handlers. Data access goes through services.py (sync ORM) via sync_to_async."""

from __future__ import annotations

import re

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from asgiref.sync import sync_to_async

from accounts.services import ref_code_from_param
from botquiz.services import mark_reachable
from classes.services import code_from_param as class_code
from duels.services import code_from_param

from . import services
from .texts import t

router = Router(name="yodflip")
TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


def open_button(text: str, path: str = "/") -> InlineKeyboardMarkup | None:
    url = services.webapp_url(path)
    if not url:
        return None
    # Telegram accepts only HTTPS for Web App buttons; plain link otherwise (local dev).
    btn = (
        InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
        if url.startswith("https://")
        else InlineKeyboardButton(text=text, url=url)
    )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


async def lang_of(message: Message) -> str:
    u = message.from_user
    return await sync_to_async(services.user_language)(u.id, u.language_code or "") if u else "uz"


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    lang = await lang_of(message)
    if message.from_user:
        await sync_to_async(mark_reachable)(message.from_user.id)
    code = code_from_param(command.args)
    if code:  # t.me/<bot>?start=duel_<code>
        await message.answer(t(lang, "duel_invited"), reply_markup=open_button(t(lang, "duel_open"), f"/duel/{code}"))
        return
    code = class_code(command.args)
    if code:  # t.me/<bot>?start=class_<code>
        await message.answer(t(lang, "class_invited"), reply_markup=open_button(t(lang, "class_join"), f"/join/{code}"))
        return
    name = message.from_user.first_name if message.from_user else ""
    ref = ref_code_from_param(command.args)  # t.me/<bot>?start=ref_<code> (share card QR code)
    path = f"/?ref={ref}" if ref else "/"
    await message.answer(t(lang, "welcome", name=name), reply_markup=open_button(t(lang, "open"), path))


@router.message(Command("duel"))
async def cmd_duel(message: Message) -> None:
    lang = await lang_of(message)
    await message.answer(t(lang, "duel_help"), reply_markup=open_button(t(lang, "duel_new"), "/duel"))


@router.message(Command("daily"))
async def cmd_daily(message: Message) -> None:
    lang = await lang_of(message)
    data = await sync_to_async(services.daily)()
    lines = [t(lang, "daily_title")]
    for track, label in (("en", "EN ·"), ("de", "DE ·")):
        lines.append(f"\n{label} {', '.join(data.get(track, []))}")
    await message.answer("\n".join(lines), reply_markup=open_button(t(lang, "play_daily"), "/play/daily"))


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    lang = await lang_of(message)
    s = await sync_to_async(services.stats)(message.from_user.id)
    if not s["registered"]:
        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
        return
    en, de = s["tracks"]["en"], s["tracks"]["de"]
    await message.answer(
        t(
            lang,
            "stats",
            level=s["level"],
            xp=s["xp"],
            streak=s["streak"],
            en_learned=en["learned"],
            en_total=en["total"],
            de_learned=de["learned"],
            de_total=de["total"],
            today="✅" if s["played_today"] else "⏳",
        ),
        reply_markup=open_button(t(lang, "open"), "/profile"),
    )


@router.message(Command("review"))
async def cmd_review(message: Message) -> None:
    lang = await lang_of(message)
    s = await sync_to_async(services.stats)(message.from_user.id)
    if not s["registered"]:
        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
        return
    en, de = s["tracks"]["en"]["due"], s["tracks"]["de"]["due"]
    text = t(lang, "review", en=en, de=de) if en or de else t(lang, "review_none")
    await message.answer(text, reply_markup=open_button(t(lang, "play_review"), "/play/review"))


@router.message(Command("remind"))
async def cmd_remind(message: Message, command: CommandObject) -> None:
    lang = await lang_of(message)
    arg = (command.args or "").strip().lower()
    m = TIME_RE.fullmatch(arg)
    if arg != "off" and not m:
        await message.answer(t(lang, "remind_help"))
        return
    value = "off" if arg == "off" else f"{int(m.group(1)):02d}:{m.group(2)}"
    stored = await sync_to_async(services.set_reminder)(message.from_user.id, value)
    if stored is None:
        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
    elif stored == "off":
        await message.answer(t(lang, "remind_off"))
    else:
        await message.answer(t(lang, "remind_set", time=stored))
