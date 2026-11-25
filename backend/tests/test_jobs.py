"""Daily reminders, run log + status endpoint, lock and in-app scheduler."""

import importlib.util
import logging
import types
from datetime import UTC, date, datetime, time, timedelta

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.methods import SendMessage
from django.conf import settings as dj_settings
from rest_framework.test import APIClient

from accounts.models import User
from botquiz import sender
from botquiz import services as quiz
from botquiz.models import QuizSettings
from jobs import locks, scheduler
from jobs import services as jobs
from jobs.models import CronRunLog, JobLock
from telegram_bot import delivery, reminders

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-token-for-tests-000000"
DAY = date(2026, 3, 2)


@pytest.fixture(autouse=True)
def bot_settings(settings, monkeypatch):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.PUBLIC_URL = "https://yodflip.example.com"
    settings.BOT_CRON_SECRET = "cron-secret"
    settings.NAPS = []

    async def no_sleep(s):
        settings.NAPS.append(s)

    for module in (sender, reminders):
        monkeypatch.setattr(module, "sleep", no_sleep)
    return settings


class Telegram:
    def __init__(self):
        self.calls, self.fail = [], {}

    @property
    def chats(self):
        return [c.chat_id for c in self.calls if isinstance(c, SendMessage)]


@pytest.fixture
def tg(monkeypatch):
    api = Telegram()

    async def fake_call(self, method, request_timeout=None):
        errors = api.fail.get(getattr(method, "chat_id", None))
        if errors:
            raise errors.pop(0)(method)
        api.calls.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    return api


def at(monkeypatch, *args):
    """UTC time; Tashkent is +5."""
    now = datetime(*args, tzinfo=UTC)
    monkeypatch.setattr("django.utils.timezone.now", lambda: now)
    return now


def person(tg_id, remind=time(19, 0), tz="Asia/Tashkent", **kw):
    u = User.objects.create_user(telegram_id=tg_id, reminder_time=remind, **kw)
    QuizSettings.objects.create(user=u, enabled=False, timezone=tz)
    return u


def cron(path=""):
    return APIClient().get(f"/bot/cron/cron-secret/{path}").json()


# --- selection ------------------------------------------------------------------------------
def test_reminder_selection_reasons(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 30)  # 19:30 in Tashkent
    person(1)
    person(2, remind=None)
    person(3, remind=time(19, 31))
    person(4, last_active_date=DAY)
    person(5, last_reminder_date=DAY)
    person(6, is_active=False)
    QuizSettings.objects.filter(user=person(7)).update(bot_blocked=True)
    QuizSettings.objects.filter(user=person(8)).update(last_sent_at=datetime(2026, 3, 2, 4, tzinfo=UTC))
    person(9, last_active_date=DAY - timedelta(days=1), last_reminder_date=DAY - timedelta(days=1))
    User.objects.create_user(email="web@example.com", reminder_time=time(0, 0))  # no Telegram
    due, skipped = reminders.select_due()
    assert [u.telegram_id for u in due] == [1, 9]
    assert skipped == {
        "reminder_off": 1,
        "not_yet_time": 1,
        "played_today": 1,
        "already_sent_today": 1,
        "inactive_account": 1,
        "bot_blocked": 1,
        "quiz_sent_today": 1,
    }
    cron()
    assert tg.chats == [1, 9]


def test_reminder_time_is_in_the_users_timezone(tg, monkeypatch):
    person(1, tz="Asia/Tashkent")
    person(2, tz="Europe/Berlin")
    person(3, tz="not/a-zone")  # falls back to Tashkent
    at(monkeypatch, 2026, 3, 2, 13, 59)  # 18:59 Tashkent
    cron()
    assert tg.chats == []
    at(monkeypatch, 2026, 3, 2, 14, 0)
    cron()
    assert tg.chats == [1, 3]
    at(monkeypatch, 2026, 3, 2, 18, 0)  # 19:00 Berlin
    cron()
    assert tg.chats == [1, 3, 2]


def test_user_without_quiz_settings_gets_the_reminder(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 4, 30)  # 09:30: no quiz yet
    User.objects.create_user(telegram_id=1, reminder_time=time(9, 0))
    cron()
    assert tg.chats == [1]


def test_once_per_day_and_again_the_next_day(tg, monkeypatch):
    u = person(1)
    at(monkeypatch, 2026, 3, 2, 14, 0)
    for path in ("", "quiz/", "", "quiz"):  # both URLs run the same idempotent job
        cron(path)
    assert tg.chats == [1]
    u.refresh_from_db()
    assert u.last_reminder_date == DAY
    at(monkeypatch, 2026, 3, 3, 14, 0)
    cron()
    assert tg.chats == [1, 1]


def test_overlapping_claim_and_playing_in_between(monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    u = person(1)
    assert reminders.claim(u, DAY) is True
    assert reminders.claim(u, DAY) is False
    v = person(2)
    User.objects.filter(pk=v.pk).update(last_active_date=DAY)
    assert reminders.claim(v, DAY) is False


# --- errors ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "error,result,sent_again",
    [
        (lambda m: TelegramForbiddenError(method=m, message="bot was blocked"), "blocked", False),
        (lambda m: TelegramBadRequest(method=m, message="Bad Request: chat not found"), "blocked", False),
        (lambda m: TelegramBadRequest(method=m, message="Bad Request: whatever"), "failed", False),
        (lambda m: TelegramNetworkError(method=m, message="Request timeout error"), "failed", False),
        (lambda m: RuntimeError("?"), "failed", False),
        (lambda m: TelegramNetworkError(method=m, message="ClientConnectorError: no route"), "retry_later", True),
        (lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=900), "retry_later", True),
        (lambda m: TelegramUnauthorizedError(method=m, message="Unauthorized"), "failed", True),
    ],
)
def test_errors_are_counted_and_only_undelivered_messages_are_retried(tg, monkeypatch, error, result, sent_again):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    u = person(1)
    tg.fail[1] = [error]
    r = cron()["reminders"]
    assert r[result] == 1 and r["sent"] == 0 and sum(r["errors"].values()) == 1
    assert QuizSettings.objects.get(user=u).bot_blocked is (result == "blocked")
    row = CronRunLog.objects.get(job="reminders")
    assert row.failed == 1 and row.details["errors"]
    cron()
    assert tg.chats == ([1] if sent_again else [])


def test_429_is_retried_in_the_same_run(tg, monkeypatch, bot_settings):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    person(1)
    tg.fail[1] = [lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=3)]
    assert cron()["reminders"]["sent"] == 1
    assert 3 in bot_settings.NAPS


def test_one_failing_user_does_not_stop_the_others(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    for i in (1, 2, 3):
        person(i)
    tg.fail[2] = [lambda m: RuntimeError("boom")]
    assert cron()["reminders"]["sent"] == 2
    assert tg.chats == [1, 3]


def test_any_message_makes_the_user_reachable_again(tg):
    from telegram_bot.views import _note_reachable

    u = person(1)
    QuizSettings.objects.filter(user=u).update(bot_blocked=True)
    _note_reachable({"message": {"chat": {"type": "group"}, "from": {"id": 1}}})
    assert QuizSettings.objects.get(user=u).bot_blocked is True
    _note_reachable({"callback_query": {"from": {"id": 1}, "message": {"chat": {"type": "private"}}}})
    assert QuizSettings.objects.get(user=u).bot_blocked is False


# --- quiz -----------------------------------------------------------------------------------
def test_quiz_catches_up_after_a_missed_hour(monkeypatch):
    u = User.objects.create_user(telegram_id=1)
    conf = QuizSettings.objects.create(user=u, hour=19)
    now = datetime(2026, 3, 2, tzinfo=UTC)
    for hour, expected in [(13, "not_yet_time"), (14, None), (16, None), (17, "hour_passed")]:  # UTC
        at(monkeypatch, 2026, 3, 2, hour)
        assert quiz.skip_reason(conf, now.replace(hour=hour)) == expected


def test_broken_quiz_neither_stops_the_run_nor_uses_up_the_day(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    for i in (1, 2):
        u = User.objects.create_user(telegram_id=i, reminder_time=time(9, 0))
        QuizSettings.objects.create(user=u)
    monkeypatch.setattr(quiz, "new_session", lambda user: 1 / 0)
    r = cron()
    assert r["quiz"]["failed"] == 2
    assert QuizSettings.objects.filter(last_sent_on__isnull=True).count() == 2
    assert tg.chats == [1, 2]  # the plain reminder still goes out


def test_no_quiz_words_does_not_block_the_reminder(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    u = User.objects.create_user(telegram_id=1, reminder_time=time(9, 0))
    QuizSettings.objects.create(user=u)
    monkeypatch.setattr(quiz, "new_session", lambda user: None)
    cron()
    assert tg.chats == [1]


def test_crash_of_one_part_is_logged_and_the_rest_runs(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    person(1)
    monkeypatch.setattr("botquiz.sender.send_due_quizzes", lambda budget: 1 / 0)
    monkeypatch.setattr("duels.services.expire_due", lambda: 1 / 0)
    r = cron()
    assert r["ok"] is False and "ZeroDivisionError" in r["quiz"]["error"]
    assert r["reminders"]["sent"] == 1


# --- log + status ---------------------------------------------------------------------------
def test_status_endpoint(tg, monkeypatch):
    assert APIClient().get("/bot/cron/wrong/status/").status_code == 403
    s = cron("status/")
    assert s["last_run"] is None and s["jobs"]["reminders"]["runs"] == []
    person(1)
    person(2, remind=None)
    for minute in range(9):
        at(monkeypatch, 2026, 3, 2, 14, minute)
        cron()
    s = cron("status")
    runs = s["jobs"]["reminders"]["runs"]
    assert len(runs) == 7 and runs[0]["at"] == "2026-03-02T19:08:00+05:00"
    assert runs[0]["skip_reasons"] == {"already_sent_today": 1, "reminder_off": 1} and runs[0]["skipped"] == 2
    first = s["jobs"]["reminders"]["last_run_with_matches"]
    assert (first["matched"], first["sent"], first["failed"]) == (1, 1, 0)
    assert s["users"] == {"with_telegram": 2, "reminder_enabled": 1, "quiz_enabled": 0, "bot_blocked": 0}
    assert s["minutes_since_last_run"] == 0 and s["bot_token_set"] is True
    assert "cron-secret" not in str(s) and TOKEN not in str(s)
    assert tg.chats == [1]


def test_missing_token_is_visible(bot_settings):
    bot_settings.TELEGRAM_BOT_TOKEN = ""
    assert cron()["detail"] == "bot_disabled"
    assert cron("status/")["jobs"]["reminders"]["runs"][0]["error"] == "bot_disabled"


def test_run_is_logged_without_secrets(tg, monkeypatch, caplog):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    person(1)
    tg.fail[1] = [lambda m: RuntimeError(f"https://api.telegram.org/bot{TOKEN}/sendMessage")]
    with caplog.at_level(logging.INFO):
        cron()
    assert "Job reminders (cron): matched=1 sent=0 failed=1" in caplog.text
    assert TOKEN not in caplog.text and "cron-secret" not in caplog.text
    assert TOKEN not in str(CronRunLog.objects.values_list("details", flat=True))


def test_token_is_redacted_in_tracebacks():
    from core.logging import RedactingFormatter

    try:
        raise ValueError(f"bot{TOKEN}")
    except ValueError as exc:
        record = logging.LogRecord("x", logging.ERROR, "f", 1, "oops", (), (type(exc), exc, exc.__traceback__))
    assert TOKEN not in RedactingFormatter("%(message)s").format(record)


# --- lock + scheduler -----------------------------------------------------------------------
def test_lock(monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    token = locks.acquire("x", 60)
    assert token and locks.acquire("x", 60) is None and locks.holder("x") == token
    locks.release("x", "someone-else")
    assert locks.acquire("x", 60) is None
    assert locks.renew("x", token, 120) is True
    at(monkeypatch, 2026, 3, 2, 14, 1)
    assert locks.acquire("x", 60) is None  # renewed
    at(monkeypatch, 2026, 3, 2, 14, 3)  # the owner died
    second = locks.acquire("x", 60)
    assert second and locks.renew("x", token, 60) is False
    locks.release("x", second)
    assert locks.holder("x") == "" and locks.acquire("x", 60)


def test_lock_prevents_a_double_run(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    person(1)
    token = locks.acquire(jobs.LOCK, 60)
    assert cron()["detail"] == "already_running"
    assert jobs.run_all("scheduler")["detail"] == "already_running"
    assert tg.chats == [] and not CronRunLog.objects.exists()
    locks.release(jobs.LOCK, token)
    assert cron()["sent"] == 1
    assert locks.holder(jobs.LOCK) == ""  # released afterwards


def test_lock_is_released_when_a_run_crashes(tg, monkeypatch):
    monkeypatch.setattr(jobs, "_parts", lambda deadline: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        jobs.run_all()
    assert locks.holder(jobs.LOCK) == ""


def test_scheduler_slot_is_run_by_one_worker(tg, monkeypatch, bot_settings):
    bot_settings.SCHEDULER_EVERY_MINUTES = 60
    runs = []
    monkeypatch.setattr(scheduler, "run_all", runs.append)
    at(monkeypatch, 2026, 3, 2, 14, 1)
    assert [scheduler.tick() for _ in range(4)] == [True, False, False, False]  # 4 workers
    at(monkeypatch, 2026, 3, 2, 14, 59)
    assert scheduler.tick() is False
    at(monkeypatch, 2026, 3, 2, 15, 0)
    assert scheduler.tick() is True
    assert runs == ["scheduler", "scheduler"] and JobLock.objects.count() == 1


def test_scheduler_and_cron_together_never_send_twice(tg, monkeypatch):
    at(monkeypatch, 2026, 3, 2, 14, 0)
    person(1)
    assert scheduler.tick() is True
    cron()
    cron("quiz/")
    assert tg.chats == [1]
    assert set(CronRunLog.objects.values_list("trigger", flat=True)) == {"cron", "scheduler"}


def test_scheduler_slots(bot_settings):
    t = datetime(2026, 3, 2, 14, 37, tzinfo=UTC)
    bot_settings.SCHEDULER_EVERY_MINUTES = 10
    assert scheduler.slot_for(t) == "2026-03-02T14:30"
    bot_settings.SCHEDULER_EVERY_MINUTES = 60
    assert scheduler.slot_for(t) == "2026-03-02T14:00"


def test_scheduler_disabled_without_env(bot_settings, monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, **kw):
            assert kw["daemon"] is True

        def start(self):
            started.append(1)

        def is_alive(self):
            return True

    monkeypatch.setattr(scheduler, "_thread", None)
    monkeypatch.setattr(scheduler.threading, "Thread", FakeThread)
    assert dj_settings.ALWAYS_ON_SCHEDULER is False  # the default
    assert scheduler.start() is None and started == []
    bot_settings.ALWAYS_ON_SCHEDULER = True
    assert scheduler.start() is not None
    scheduler.start()  # a second call doesn't start a second thread
    assert started == [1]


def test_gunicorn_starts_the_scheduler_in_each_worker(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "start", lambda: calls.append(1))
    spec = importlib.util.spec_from_file_location("gconf", dj_settings.BASE_DIR / "gunicorn.conf.py")
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)
    conf.post_worker_init(types.SimpleNamespace(log=logging.getLogger("x")))
    assert calls == [1]


def test_pace_is_at_most_25_per_second():
    assert delivery.PACE >= 1 / 25
