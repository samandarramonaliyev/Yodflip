"""In-chat quiz: one message, edited in place. Callback data: q*:<session id>:... (< 64 bytes)."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async
from django.conf import settings

from botquiz import sender
from botquiz import services as quiz
from botquiz.models import QUESTION_CHOICES
from words.translations import allowed_translation_langs

from . import services
from .texts import t

log = logging.getLogger(__name__)
router = Router(name="quiz")

FLAGS = {"uz": "🇺🇿", "ru": "🇷🇺", "en": "🇬🇧", "de": "🇩🇪"}


def _b(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def invite_markup(lang: str, sid: str) -> InlineKeyboardMarkup:
    return _kb(
        [_b(t(lang, "quiz_start"), f"qs:{sid}")],
        [_b(t(lang, "quiz_later"), f"ql:{sid}"), _b(t(lang, "quiz_off_btn"), "qx")],
    )


def new_quiz_markup(lang: str) -> InlineKeyboardMarkup:
    return _kb([_b(t(lang, "quiz_new"), "qm:0")])


def question_text(lang: str, s) -> str:
    q = s.questions[s.index]
    head = f"{s.index + 1}/{len(s.questions)}"
    if q["kind"] == "art":
        return f"{head} · 🇩🇪 ___ {q['prompt']} — {t(lang, 'quiz_article')}"
    if q["kind"] == "fwd":
        return f"{head} · {FLAGS[s.track]} {q['prompt']} — {t(lang, 'quiz_translation')}"
    return f"{head} · {FLAGS[s.translation_lang]} {q['prompt']} — {t(lang, f'quiz_in_{s.track}')}"


def question_markup(s) -> InlineKeyboardMarkup:
    q = s.questions[s.index]
    buttons = [_b(o[:60], f"qa:{s.sid}:{s.index}:{n}") for n, o in enumerate(q["options"])]
    return _kb(buttons) if q["kind"] == "art" else _kb(*[[b] for b in buttons])


def feedback_text(lang: str, r: dict) -> str:
    q = r["question"]
    lines = [t(lang, "quiz_right" if r["correct"] else "quiz_wrong")]
    if not r["correct"]:
        lines.append(f"✖️ {q['options'][r['choice']]}")
    lines.append(f"{q['term']} — {q['tr']}")
    if q["example"]:
        lines.append(f"\n💬 {q['example']}")
        if q["example_tr"]:
            lines.append(q["example_tr"])
    return "\n".join(lines)


def summary_markup(lang: str) -> InlineKeyboardMarkup:
    from .handlers import open_button

    app = open_button(t(lang, "quiz_continue"), "/")
    return _kb(*(app.inline_keyboard if app else []), [_b(t(lang, "quiz_more"), "qm:1")])


async def edit(bot: Bot, cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    if cb.message is None:
        return
    try:
        await bot.edit_message_text(
            text, chat_id=cb.message.chat.id, message_id=cb.message.message_id, reply_markup=markup
        )
    except TelegramBadRequest as exc:  # not modified / message too old
        log.info("Quiz edit failed: %s", exc)


async def lang_for(user) -> str:
    return await sync_to_async(services.user_language)(user.id, user.language_code or "")


# --------------------------------------------------------------------------- /quiz
def _menu(lang: str, conf, track: str) -> tuple[str, InlineKeyboardMarkup]:
    days = t(lang, "quiz_days").split()
    quiet = ", ".join(days[d] for d in conf.quiet_days) or "—"
    text = t(
        lang,
        "quiz_menu",
        state=t(lang, "quiz_on" if conf.enabled else "quiz_off_state"),
        hour=f"{conf.hour:02d}:00",
        tz=conf.timezone,
        n=conf.questions,
        quiet=quiet,
    )
    langs = allowed_translation_langs(track)
    return text, _kb(
        [_b(t(lang, "quiz_turn_off" if conf.enabled else "quiz_turn_on"), "qc:on:")],
        [_b("🕐 −1", "qc:h:-"), _b(f"{conf.hour:02d}:00", "qc:noop:"), _b("🕐 +1", "qc:h:+")],
        [_b(f"{'✅ ' if conf.questions == n else ''}{n}", f"qc:n:{n}") for n in QUESTION_CHOICES],
        [_b(f"{'✅ ' if conf.translation_lang == x else ''}{FLAGS[x]}", f"qc:l:{x}") for x in langs],
        [_b(f"{'🔕' if d in conf.quiet_days else ''}{days[d]}", f"qc:d:{d}") for d in range(7)],
    )


@router.message(Command("quiz"))
async def cmd_quiz(message: Message, command: CommandObject) -> None:
    lang = await lang_for(message.from_user)
    user = await sync_to_async(quiz.user_by_tg)(message.from_user.id)
    if user is None:
        from .handlers import open_button

        await message.answer(t(lang, "not_registered"), reply_markup=open_button(t(lang, "open"), "/"))
        return
    await sync_to_async(quiz.mark_reachable)(message.from_user.id)
    arg = (command.args or "").strip().lower()
    if arg in ("settings", "sozlama", "sozlamalar", "настройки"):
        conf = await sync_to_async(quiz.settings_for)(user)
        text, markup = _menu(lang, conf, user.active_track)
        await message.answer(text, reply_markup=markup)
        return
    if arg in ("on", "off"):
        await sync_to_async(quiz.update_settings)(user, enabled=arg == "on")
        await message.answer(t(lang, "quiz_enabled" if arg == "on" else "quiz_disabled"))
        return
    s = await sync_to_async(quiz.new_session)(user)
    if s is None:
        await message.answer(t(lang, "review_none"))
        return
    s = await sync_to_async(quiz.begin)(message.from_user.id, s.sid)
    await message.answer(question_text(lang, s), reply_markup=question_markup(s))


# --------------------------------------------------------------------------- buttons
@router.callback_query(F.data.startswith("qs:"))
async def on_start(cb: CallbackQuery, bot: Bot) -> None:
    lang = await lang_for(cb.from_user)
    s = await sync_to_async(quiz.begin)(cb.from_user.id, cb.data.split(":")[1])
    if s is None:
        await stale(cb, bot, lang)
        return
    await cb.answer()
    await edit(bot, cb, question_text(lang, s), question_markup(s))


@router.callback_query(F.data.startswith("ql:"))
async def on_later(cb: CallbackQuery, bot: Bot) -> None:
    lang = await lang_for(cb.from_user)
    sid = cb.data.split(":")[1]
    await cb.answer()
    await edit(bot, cb, t(lang, "quiz_later_text"), _kb([_b(t(lang, "quiz_start"), f"qs:{sid}")]))


@router.callback_query(F.data == "qx")
async def on_off(cb: CallbackQuery, bot: Bot) -> None:
    lang = await lang_for(cb.from_user)
    user = await sync_to_async(quiz.user_by_tg)(cb.from_user.id)
    if user:
        await sync_to_async(quiz.update_settings)(user, enabled=False)
    await cb.answer()
    await edit(bot, cb, t(lang, "quiz_disabled"))


@router.callback_query(F.data.startswith("qm:"))
async def on_more(cb: CallbackQuery, bot: Bot) -> None:
    """ "Yana 5 ta" (qm:1) or a whole new quiz (qm:0) in the same message."""
    lang = await lang_for(cb.from_user)
    user = await sync_to_async(quiz.user_by_tg)(cb.from_user.id)
    count = quiz.MORE if cb.data == "qm:1" else None
    s = await sync_to_async(quiz.new_session)(user, count) if user else None
    await cb.answer()
    if s is None:
        await edit(bot, cb, t(lang, "review_none"))
        return
    s = await sync_to_async(quiz.begin)(cb.from_user.id, s.sid)
    await edit(bot, cb, question_text(lang, s), question_markup(s))


async def stale(cb: CallbackQuery, bot: Bot, lang: str) -> None:
    await cb.answer(t(lang, "quiz_stale"))
    await edit(bot, cb, t(lang, "quiz_stale_text"), new_quiz_markup(lang))


@router.callback_query(F.data.startswith("qa:"))
async def on_answer(cb: CallbackQuery, bot: Bot) -> None:
    lang = await lang_for(cb.from_user)
    try:
        _, sid, index, choice = cb.data.split(":")
        r = await sync_to_async(quiz.answer)(cb.from_user.id, sid, int(index), int(choice))
    except ValueError:
        r = {"stale": "expired"}
    if r.get("stale") == "expired":
        await stale(cb, bot, lang)
        return
    if r.get("stale"):  # pressed twice: the quiz itself goes on
        await cb.answer(t(lang, "quiz_stale"))
        return
    await cb.answer("✅" if r["correct"] else "❌")
    await edit(bot, cb, feedback_text(lang, r))
    await sender.sleep(settings.QUIZ_FEEDBACK_SECONDS)
    if "summary" in r:
        await edit(bot, cb, t(lang, "quiz_summary", **r["summary"]), summary_markup(lang))
    else:
        await edit(bot, cb, question_text(lang, r["session"]), question_markup(r["session"]))


@router.callback_query(F.data.startswith("qc:"))
async def on_setting(cb: CallbackQuery, bot: Bot) -> None:
    lang = await lang_for(cb.from_user)
    user = await sync_to_async(quiz.user_by_tg)(cb.from_user.id)
    await cb.answer()
    _, action, value = (cb.data.split(":") + ["", ""])[:3]
    if user is None or action == "noop":
        return
    conf = await sync_to_async(quiz.menu_action)(user, action, value)
    text, markup = _menu(lang, conf, user.active_track)
    await edit(bot, cb, text, markup)
