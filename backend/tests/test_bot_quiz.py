"""In-chat bot quiz: hourly schedule, one edited message, stale buttons, 403 / 429, same data as the app."""

import json
from datetime import UTC, datetime, time, timedelta

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TranslationPreference, User
from botquiz import sender
from botquiz import services as quiz
from botquiz.models import QuizSession, QuizSettings
from gamification.models import DailyActivity, GameSession
from telegram_bot import services
from words.models import Pack, UserLevelWord, UserWord, Word, WordTranslation

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-token-for-tests"


@pytest.fixture(autouse=True)
def bot_settings(settings, monkeypatch):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.PUBLIC_URL = "https://yodflip.example.com"
    settings.BOT_CRON_SECRET = "cron-secret"
    naps = []

    async def no_sleep(s):
        naps.append(s)

    monkeypatch.setattr(sender, "sleep", no_sleep)
    settings.NAPS = naps
    return settings


class Telegram:
    def __init__(self):
        self.calls, self.fail = [], {}  # fail: {chat_id: [exceptions]}

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]


@pytest.fixture
def tg(monkeypatch):
    api = Telegram()

    async def fake_call(self, method, request_timeout=None):
        errors = api.fail.get(getattr(method, "chat_id", None))
        if isinstance(method, SendMessage) and errors:
            raise errors.pop(0)(method)
        api.calls.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    return api


@pytest.fixture
def words(db):
    out = []
    for track in ("en", "de"):
        pack = Pack.objects.create(track=track, level="A1", slug="p", name_uz="p", name_en="p", name_ru="p")
        for i in range(15):
            w = Word.objects.create(
                track=track,
                level="A1",
                pack=pack,
                word=f"{track}word{i}",
                article="der" if track == "de" else "",
                part_of_speech="noun",
                definition=f"def {i}",
                translation_uz=f"soz{i}",
                example=f"Example {i}.",
                example_uz=f"Misol {i}.",
            )
            for lang in ("uz", "ru", "de" if track == "en" else "en"):
                WordTranslation.objects.create(
                    word=w, lang=lang, text=f"{lang}tr{i}" if lang != "uz" else f"soz{i}", example_translation=f"ex{i}"
                )
            out.append(w)
    return out


@pytest.fixture
def player(db):
    return User.objects.create_user(telegram_id=777, display_name="Ali")


def at(monkeypatch, *args):
    now = datetime(*args, tzinfo=UTC)
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    return now


def cron():
    return APIClient().get("/bot/cron/cron-secret/quiz/")


def update(payload):
    s = services.webhook_secret()
    return APIClient().post(
        f"/bot/webhook/{s}/",
        data=json.dumps({"update_id": 1, **payload}),
        content_type="application/json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=s,
    )


def message(text, uid=777):
    ent = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    chat, frm = {"id": uid, "type": "private"}, {"id": uid, "is_bot": False, "first_name": "A", "language_code": "uz"}
    update({"message": {"message_id": 1, "date": 1, "chat": chat, "from": frm, "text": text, "entities": ent}})


def press(data, uid=777, message_id=50):
    chat, frm = {"id": uid, "type": "private"}, {"id": uid, "is_bot": False, "first_name": "A", "language_code": "uz"}
    msg = {"message_id": message_id, "date": 1700000000, "chat": chat, "text": "x"}
    cb = {"id": "1", "from": frm, "message": msg, "chat_instance": "1", "data": data}
    update({"callback_query": cb})


def buttons(method):
    return [b for row in method.reply_markup.inline_keyboard for b in row]


# --- schedule -------------------------------------------------------------------------------
def test_cron_is_idempotent_and_needs_the_secret(tg, words, player, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 5)  # 19:05 in Tashkent
    assert APIClient().get("/bot/cron/wrong/quiz/").status_code == 403
    assert cron().json()["sent"] == 1
    assert cron().json()["sent"] == 0 and cron().json()["sent"] == 0
    assert len(tg.of(SendMessage)) == 1
    m = tg.calls[0]
    assert m.chat_id == 777 and "8 ta so'z" in m.text
    assert [b.text[0] for b in buttons(m)] == ["▶", "⏰", "🔕"]
    assert all(len(b.callback_data.encode()) < 64 for b in buttons(m))
    at(monkeypatch, 2026, 3, 3, 14, 5)  # next day
    assert cron().json()["sent"] == 1


def test_overlapping_cron_calls_send_once(words, player):
    conf = quiz.settings_for(player)
    day = timezone.localdate()
    assert quiz.claim(conf.id, day) is not None
    assert quiz.claim(conf.id, day) is None


def test_user_hour_matches_in_their_timezone(tg, words, monkeypatch):
    rows = [("Asia/Tashkent", 19), ("Europe/Berlin", 15), ("America/New_York", 9), ("Asia/Tashkent", 20), ("UTC", 19)]
    for n, (tz, hour) in enumerate(rows):
        u = User.objects.create_user(telegram_id=n + 1, display_name=str(n))
        QuizSettings.objects.create(user=u, timezone=tz, hour=hour)
    at(monkeypatch, 2026, 3, 2, 14, 0)  # Tashkent 19, Berlin 15, New York 9, UTC 14
    assert cron().json()["sent"] == 3
    assert {m.chat_id for m in tg.of(SendMessage)} == {1, 2, 3}


def test_not_sent_when_played_off_quiet_or_blocked(tg, words, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)  # a Monday
    for n, (user_kw, conf_kw) in enumerate(
        [
            ({"last_active_date": timezone.localdate()}, {}),
            ({}, {"enabled": False}),
            ({}, {"quiet_days": [0]}),
            ({}, {"bot_blocked": True}),
            ({}, {"quiet_days": [6]}),
        ]
    ):
        u = User.objects.create_user(telegram_id=n + 1, **user_kw)
        QuizSettings.objects.create(user=u, **conf_kw)
    cron()
    assert [m.chat_id for m in tg.of(SendMessage)] == [5]


def test_403_marks_inactive_and_writing_again_reactivates(tg, words, player, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    tg.fail[777] = [lambda m: TelegramForbiddenError(method=m, message="bot was blocked by the user")]
    assert cron().json()["blocked"] == 1
    assert QuizSettings.objects.get(user=player).bot_blocked is True
    at(monkeypatch, 2026, 3, 3, 14, 0)
    assert cron().json()["due"] == 0
    message("/start")
    assert QuizSettings.objects.get(user=player).bot_blocked is False


def test_429_is_retried_after_the_given_time(tg, words, player, monkeypatch, bot_settings):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    tg.fail[777] = [lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=3)]
    assert cron().json()["sent"] == 1
    assert 3 in bot_settings.NAPS and len(tg.of(SendMessage)) == 1


def test_429_longer_than_the_budget_is_sent_by_the_next_call(tg, words, player, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    tg.fail[777] = [lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=900)]
    assert cron().json()["retry_later"] == 1
    assert cron().json()["sent"] == 1


def test_unknown_error_never_sends_twice(tg, words, player, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    tg.fail[777] = [lambda m: RuntimeError("timeout")]
    assert cron().json()["failed"] == 1
    assert cron().json()["sent"] == 0


def test_plain_reminder_is_skipped_after_a_quiz(tg, words, player, monkeypatch):
    other = User.objects.create_user(telegram_id=888, reminder_time=time(0, 0))
    QuizSettings.objects.create(user=other, enabled=False)
    player.reminder_time = time(0, 0)
    player.save()
    at(monkeypatch, 2026, 3, 2, 14, 0)
    cron()
    r = APIClient().get("/bot/cron/cron-secret/")  # the old endpoint still works
    assert r.json()["sent"] == 1
    assert [m.chat_id for m in tg.of(SendMessage)] == [777, 888]


# --- playing --------------------------------------------------------------------------------
def play(s, right=True):
    s.refresh_from_db()
    a = s.questions[s.index]["answer"]
    press(f"qa:{s.sid}:{s.index}:{a if right else (a + 1) % len(s.questions[s.index]['options'])}")
    s.refresh_from_db()


def test_whole_quiz_is_one_edited_message(tg, words, player):
    message("/quiz")
    assert len(tg.of(SendMessage)) == 1
    s = QuizSession.objects.get()
    assert tg.calls[0].text.startswith("1/8 · ")
    assert all(len(b.callback_data.encode()) < 64 for b in buttons(tg.calls[0]))
    for n in range(8):
        play(s, right=n < 6)
    assert len(tg.of(SendMessage)) == 1  # never a second message
    edits = tg.of(EditMessageText)
    assert len(edits) == 16 and {e.message_id for e in edits} == {50}
    assert edits[0].text.startswith("✅") and "💬 Example" in edits[0].text and "ex" in edits[0].text
    assert edits[1].text.startswith("2/8")
    assert edits[14].text.startswith("❌")
    assert len(tg.of(AnswerCallbackQuery)) == 8
    last = edits[-1]
    player.refresh_from_db()
    assert last.text == f"6/8 ✅ · +{player.xp} XP · 🔥 streak 1 kun" and player.xp == 36
    assert buttons(last)[0].web_app.url.startswith("https://") and buttons(last)[1].callback_data == "qm:1"
    press("qm:1")
    assert QuizSession.objects.count() == 2 and len(QuizSession.objects.first().questions) == 5


def test_invite_buttons(tg, words, player):
    s = quiz.new_session(player)
    press(f"ql:{s.sid}")
    assert buttons(tg.of(EditMessageText)[-1])[0].callback_data == f"qs:{s.sid}"
    press(f"qs:{s.sid}")
    assert tg.of(EditMessageText)[-1].text.startswith("1/8")
    press("qx")
    assert QuizSettings.objects.get(user=player).enabled is False


def test_double_press_and_stale_session(tg, words, player):
    s = quiz.new_session(player)
    press(f"qs:{s.sid}")
    a = s.questions[0]["answer"]
    press(f"qa:{s.sid}:0:{a}")
    n = len(tg.of(EditMessageText))
    press(f"qa:{s.sid}:0:{a}")  # the same button again
    assert tg.of(AnswerCallbackQuery)[-1].text == "Bu savol eskirgan"
    assert len(tg.of(EditMessageText)) == n
    s.refresh_from_db()
    assert (s.index, s.correct) == (1, 1)
    QuizSession.objects.update(created_at=timezone.now() - timedelta(hours=25))
    press(f"qa:{s.sid}:1:0")
    assert tg.of(AnswerCallbackQuery)[-1].text == "Bu savol eskirgan"
    assert buttons(tg.of(EditMessageText)[-1])[0].callback_data == "qm:0"  # offers a new quiz
    press("qs:unknown")
    assert tg.of(AnswerCallbackQuery)[-1].text == "Bu savol eskirgan"


def test_another_user_cannot_answer(tg, words, player):
    User.objects.create_user(telegram_id=999)
    s = quiz.new_session(player)
    press(f"qa:{s.sid}:0:0", uid=999)
    s.refresh_from_db()
    assert s.index == 0


def test_answers_update_the_same_data_as_the_app(tg, words, player):
    w_due, w_new, w_missed = words[0], words[1], words[2]
    past = timezone.now() - timedelta(days=1)
    # due and already found: a normal Leitner step
    UserLevelWord.objects.create(user=player, word=w_due, track="en", level="A1", found_at=past)
    uw = UserWord.objects.create(
        user=player, track="en", term_key=w_due.word, term=w_due.word, word=w_due, box=2, seen=True, due_at=past
    )
    deck_uw = UserWord.objects.create(
        user=player,
        track="en",
        term_key="custom",
        term="custom",
        translation_uz="maxsus",
        box=3,
        seen=True,
        due_at=past,
    )
    for item, ok in (
        ({"term": w_due.word, "word_id": w_due.id}, True),
        ({"term": "custom", "word_id": None, "translation": "maxsus"}, False),
        ({"term": w_new.word, "word_id": w_new.id}, True),
        ({"term": w_missed.word, "word_id": w_missed.id}, False),
    ):
        q = {"kind": "fwd", "prompt": "x", "options": ["a", "b"], "answer": 0, "term": "x", "tr": "y"}
        q.update(example="", example_tr="", item=item)
        s = QuizSession.objects.create(user=player, track="en", questions=[q])
        press(f"qa:{s.sid}:0:{0 if ok else 1}")
    uw.refresh_from_db()
    deck_uw.refresh_from_db()
    assert uw.box == 3  # 2 → 3
    assert (deck_uw.box, deck_uw.miss_count) == (1, 1)  # back to box 1 = Missed
    assert UserWord.objects.get(user=player, word=w_new).box == 5  # found = learned
    assert UserLevelWord.objects.filter(user=player, found_at__isnull=False).count() == 2  # each counted once
    assert UserWord.objects.get(user=player, word=w_missed).is_missed
    player.refresh_from_db()
    assert player.streak == 1 and player.last_active_date == timezone.localdate()
    assert player.xp == 12 and DailyActivity.objects.get(user=player).games == 4
    assert GameSession.objects.filter(user=player, source="bot_quiz").count() == 4


def test_priority_no_duplicates_and_language(words, player):
    past = timezone.now() - timedelta(days=1)

    def uw(w, **kw):
        kw = {"due_at": timezone.now() + timedelta(days=9), **kw}
        return UserWord.objects.create(user=player, track="en", term_key=w.word, term=w.word, word=w, **kw)

    uw(words[0], box=2, seen=True, due_at=past)
    uw(words[1], want_to_learn=True)
    uw(words[2], box=1, miss_count=2, seen=True)
    uw(words[3], box=5, want_to_learn=True, seen=True)  # learned: not asked
    TranslationPreference.objects.create(user=player, track="en", preferred_translation_lang="ru")
    s = quiz.new_session(player, 5)
    ids = [q["item"]["word_id"] for q in s.questions]
    assert len(set(ids)) == 5 and {words[0].id, words[1].id, words[2].id} <= set(ids) and words[3].id not in ids
    assert s.translation_lang == "ru" and all(q["tr"].startswith("rutr") for q in s.questions)
    assert {q["kind"] for q in s.questions} == {"fwd", "rev"}
    assert all(len(set(q["options"])) == 4 for q in s.questions)


def test_german_articles(words, player):
    player.active_track = "de"
    player.save()
    kinds = [q["kind"] for _ in range(8) for q in quiz.new_session(player, 10).questions]
    assert {"art", "fwd", "rev"} == set(kinds)


def test_settings_api_and_bot_menu(tg, words, player, client_for):
    api = client_for(player)
    d = api.get("/api/quiz/settings/").data
    assert (d["enabled"], d["hour"], d["timezone"], d["questions"]) == (True, 19, "Asia/Tashkent", 8)
    body = {"hour": 7, "timezone": "Europe/Berlin", "questions": 10, "quiet_days": [6, 5, 6], "translation_lang": "ru"}
    r = api.patch("/api/quiz/settings/", body, format="json")
    assert r.status_code == 200 and r.data["quiet_days"] == [5, 6]
    for bad in ({"hour": 24}, {"timezone": "Mars/Base"}, {"questions": 7}, {"quiet_days": [7]}):
        assert api.patch("/api/quiz/settings/", bad, format="json").status_code == 400
    message("/quiz settings")
    assert "07:00" in tg.calls[-1].text
    for data in ("qc:h:+", "qc:n:5", "qc:l:uz", "qc:d:5", "qc:on:"):
        press(data)
    conf = QuizSettings.objects.get(user=player)
    assert (conf.hour, conf.questions, conf.translation_lang, conf.quiet_days, conf.enabled) == (8, 5, "uz", [6], False)
    message("/quiz on")
    assert QuizSettings.objects.get(user=player).enabled is True


def test_unregistered_quiz(tg):
    message("/quiz", uid=5)
    assert "hisobingiz" in tg.calls[-1].text


def test_nothing_to_ask(tg, player):
    message("/quiz")
    assert tg.calls[-1].text.startswith("🎉")
