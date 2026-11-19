"""Telegram bot running inside Django: webhook view, handlers, reminder cron, webhook setup."""

import json
from datetime import time

import httpx
import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from telegram_bot import services
from telegram_bot.setup import configure_telegram
from telegram_bot.texts import TEXTS, t

TOKEN = "123456:TEST-token-for-tests"


@pytest.fixture
def bot_settings(settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.PUBLIC_URL = "https://yodflip.example.com"
    settings.TELEGRAM_WEBHOOK_SECRET = "wh-secret"
    settings.BOT_CRON_SECRET = "cron-secret"
    return settings


@pytest.fixture
def sent(monkeypatch):
    """Capture every Bot API call instead of hitting Telegram."""
    calls = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    return calls


def update(text: str, user_id: int = 777, lang: str = "uz") -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Ali", "language_code": lang},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            if text.startswith("/")
            else [],
        },
    }


def post(text: str, secret: str | None = None, header: str | None = None, **kw):
    s = services.webhook_secret()
    return APIClient().post(
        f"/bot/webhook/{secret or s}/",
        data=json.dumps(update(text, **kw)),
        content_type="application/json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=header if header is not None else s,
    )


def test_secrets_are_telegram_safe(bot_settings):
    import re

    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", services.webhook_secret())
    assert services.webhook_secret() != services.cron_secret()


def test_texts_complete():
    for lang in TEXTS:
        assert set(TEXTS[lang]) == set(TEXTS["uz"]), lang
    assert "Yodflip" in t("uz", "welcome", name="Ali")


@pytest.mark.django_db
def test_webhook_rejects_wrong_path_or_header(bot_settings, sent):
    assert post("/start", secret="wrong").status_code == 403
    assert post("/start", header="").status_code == 403
    assert post("/start", header="wrong").status_code == 403
    assert sent == []


@pytest.mark.django_db
def test_webhook_disabled_without_token(bot_settings, sent):
    bot_settings.TELEGRAM_BOT_TOKEN = ""
    assert post("/start").status_code == 403


@pytest.mark.django_db
def test_start_sends_mini_app_button(bot_settings, sent):
    r = post("/start")
    assert r.status_code == 200
    assert len(sent) == 1 and isinstance(sent[0], SendMessage)
    msg = sent[0]
    assert msg.chat_id == 777 and "Yodflip" in msg.text
    btn = msg.reply_markup.inline_keyboard[0][0]
    assert btn.web_app.url == "https://yodflip.example.com/"


@pytest.mark.django_db
def test_stats_review_and_remind(bot_settings, sent):
    User.objects.create_user(telegram_id=777, display_name="Ali", xp=150, ui_language="en")
    post("/stats")
    assert "Level: 2 (150 XP)" in sent[-1].text  # English, from the user's profile language
    post("/review")
    assert "Nothing to review" in sent[-1].text
    post("/remind 7:30")
    assert "07:30" in sent[-1].text
    assert User.objects.get(telegram_id=777).reminder_time == time(7, 30)
    post("/remind off")
    assert User.objects.get(telegram_id=777).reminder_time is None
    post("/remind 25:00")
    assert "/remind 19:00" in sent[-1].text


@pytest.mark.django_db
def test_unregistered_user_is_invited(bot_settings, sent):
    post("/stats", user_id=999, lang="ru")
    assert "Сначала откройте приложение" in sent[-1].text


@pytest.mark.django_db
def test_daily_command_lists_words(bot_settings, sent, seeded):
    post("/daily")
    assert "EN ·" in sent[-1].text and "DE ·" in sent[-1].text


@pytest.mark.django_db
def test_reminder_cron(bot_settings, sent):
    now = timezone.localtime()
    due = User.objects.create_user(telegram_id=1, display_name="Due", reminder_time=time(0, 0))
    User.objects.create_user(
        telegram_id=2, display_name="Played", reminder_time=time(0, 0), last_active_date=now.date()
    )
    User.objects.create_user(telegram_id=3, display_name="NoReminder")
    c = APIClient()
    assert c.get("/bot/cron/wrong/").status_code == 403
    r = c.get(f"/bot/cron/{services.cron_secret()}/")
    assert r.json() == {"ok": True, "due": 1, "sent": 1}
    assert [m.chat_id for m in sent] == [1]
    due.refresh_from_db()
    assert due.last_reminder_date == now.date()
    # at most one reminder per day
    assert c.get(f"/bot/cron/{services.cron_secret()}/").json()["due"] == 0


def test_configure_telegram_sets_webhook(bot_settings):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert configure_telegram(client) is True
    methods = dict(seen)
    assert methods["setWebhook"]["url"] == f"https://yodflip.example.com/bot/webhook/{services.webhook_secret()}/"
    assert methods["setWebhook"]["secret_token"] == services.webhook_secret()
    assert methods["setChatMenuButton"]["menu_button"]["web_app"]["url"] == "https://yodflip.example.com/"
    assert {c["command"] for c in methods["setMyCommands"]["commands"]} == {
        "start",
        "daily",
        "stats",
        "review",
        "remind",
    }


def test_configure_telegram_skips_without_https_or_token(bot_settings):
    bot_settings.PUBLIC_URL = "http://localhost:8000"
    assert configure_telegram() is False
    bot_settings.TELEGRAM_BOT_TOKEN = ""
    assert configure_telegram() is False


@pytest.mark.django_db
def test_spa_does_not_swallow_bot_routes(bot_settings):
    assert APIClient().get("/bot/webhook/x/").status_code == 405  # POST only, not index.html
