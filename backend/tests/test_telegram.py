import json
import time

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from telegram_auth.verify import (
    TelegramAuthError,
    sign_init_data,
    sign_login_widget,
    verify_init_data,
    verify_login_widget,
)

TOKEN = "123456:TEST-token"


def make_init(user_id=42, auth_date=None, **extra):
    pairs = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Aziz", "username": "aziz_tg", "language_code": "uz"}),
        "auth_date": str(auth_date or int(time.time())),
        **extra,
    }
    return sign_init_data(pairs, TOKEN)


def test_valid_init_data():
    data = verify_init_data(make_init(), TOKEN)
    assert data["user"]["id"] == 42
    assert data["user"]["username"] == "aziz_tg"


def test_tampered_init_data_rejected():
    init = make_init().replace("Aziz", "Hacker")
    with pytest.raises(TelegramAuthError, match="bad_hash"):
        verify_init_data(init, TOKEN)


def test_wrong_token_rejected():
    with pytest.raises(TelegramAuthError):
        verify_init_data(make_init(), "999:other")


def test_missing_hash_rejected():
    with pytest.raises(TelegramAuthError, match="missing_hash"):
        verify_init_data("auth_date=1&user=%7B%7D", TOKEN)


def test_expired_init_data():
    old = int(time.time()) - 3 * 86400
    with pytest.raises(TelegramAuthError, match="expired"):
        verify_init_data(make_init(auth_date=old), TOKEN, max_age=86400)


def test_login_widget_verification():
    fields = {"id": 77, "first_name": "Laylo", "username": "laylo", "auth_date": int(time.time())}
    signed = sign_login_widget(fields, TOKEN)
    assert verify_login_widget(signed, TOKEN)["user"]["id"] == 77
    signed["first_name"] = "X"
    with pytest.raises(TelegramAuthError):
        verify_login_widget(signed, TOKEN)


@pytest.mark.django_db
def test_webapp_login_endpoint_creates_user(settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_MOCK = False
    c = APIClient()
    r = c.post("/api/auth/telegram/webapp/", {"init_data": make_init(555)}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["user"]["telegram_id"] == 555
    assert r.data["user"]["display_name"] == "Aziz"
    # second login reuses the same account
    c.post("/api/auth/telegram/webapp/", {"init_data": make_init(555)}, format="json")
    assert User.objects.filter(telegram_id=555).count() == 1


@pytest.mark.django_db
def test_webapp_login_bad_signature(settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_MOCK = False
    r = APIClient().post("/api/auth/telegram/webapp/", {"init_data": make_init() + "x"}, format="json")
    assert r.status_code == 401


@pytest.mark.django_db
def test_webapp_mock_mode_without_token(settings):
    settings.TELEGRAM_BOT_TOKEN = ""
    settings.TELEGRAM_MOCK = True
    r = APIClient().post("/api/auth/telegram/webapp/", {"init_data": ""}, format="json")
    assert r.status_code == 200
    assert r.data["user"]["telegram_id"] == 1000001


@pytest.mark.django_db
def test_link_telegram_merges_tg_only_account(settings, user, client_for):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_MOCK = False
    tg_user = User.objects.create_user(telegram_id=900, display_name="TG", xp=50)
    r = client_for(user).post("/api/auth/telegram/link/", {"init_data": make_init(900)}, format="json")
    assert r.status_code == 200, r.data
    user.refresh_from_db()
    assert user.telegram_id == 900
    assert user.xp == 50
    assert not User.objects.filter(pk=tg_user.pk).exists()


@pytest.mark.django_db
def test_tg_user_can_add_email(settings, client_for):
    u = User.objects.create_user(telegram_id=901, display_name="TG")
    r = client_for(u).post("/api/auth/set-email/", {"email": "tg@example.com", "password": "secret123"}, format="json")
    assert r.status_code == 200
    login = APIClient().post("/api/auth/login/", {"email": "tg@example.com", "password": "secret123"}, format="json")
    assert login.status_code == 200
    assert login.data["user"]["telegram_id"] == 901
