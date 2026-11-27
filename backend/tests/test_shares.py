"""Share cards: referral recorded once, image upload, Pillow fallback sizes, share event log, cleanup."""

import io
import json
import time
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import ensure_referral_code, record_ref_code, ref_code_from_param
from core.models import StoredFile
from gamification.models import UserAchievement
from shares.models import ShareEvent, ShareImage
from shares.views import cleanup
from telegram_auth.verify import sign_init_data

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-token"


def png(size=(1080, 1920), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, "#6C5CE7").save(buf, fmt)
    return SimpleUploadedFile("card.png", buf.getvalue(), content_type="image/png")


def tg_login(start_param, tg_id=42, **body):
    pairs = {"user": json.dumps({"id": tg_id, "first_name": "Aziz"}), "auth_date": str(int(time.time()))}
    if start_param:
        pairs["start_param"] = start_param
    payload = {"init_data": sign_init_data(pairs, TOKEN), **body}
    return APIClient().post("/api/auth/telegram/webapp/", payload, format="json")


# --------------------------------------------------------------------------- referral
def test_referral_code_is_created_once_and_exposed(api, user):
    code = api.get("/api/auth/me/").data["referral_code"]
    assert len(code) == 8 and code.isalnum()
    assert api.get("/api/auth/me/").data["referral_code"] == code
    user.refresh_from_db()
    assert ensure_referral_code(user) == code
    assert ref_code_from_param(f"ref_{code}") == code
    assert ref_code_from_param("ref_../x") == ref_code_from_param("duel_abc") == ""


def test_startapp_ref_records_invited_by_once_for_new_users(user, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    code = ensure_referral_code(user)
    assert tg_login(f"ref_{code}").status_code == 200
    new = User.objects.get(telegram_id=42)
    assert new.invited_by == user
    # another inviter's link later never overwrites it
    other = User.objects.create_user(email="b@example.com", password="x12345678")
    tg_login(f"ref_{ensure_referral_code(other)}")
    new.refresh_from_db()
    assert new.invited_by == user
    # existing users are never counted
    old = User.objects.create_user(telegram_id=43, display_name="Old")
    tg_login(f"ref_{code}", tg_id=43)
    old.refresh_from_db()
    assert old.invited_by is None
    # a bot button can't carry start_param: the app sends the ?ref= code it was opened with
    assert tg_login("", tg_id=44, ref_code=code.upper()).status_code == 200
    assert User.objects.get(telegram_id=44).invited_by == user
    # self-referral is ignored
    assert not record_ref_code(user, code)


def test_email_registration_with_ref_code_and_profile_count(user, client_for):
    code = ensure_referral_code(user)
    body = {"email": "n@example.com", "password": "Strong-pass-123", "ref_code": code}
    r = APIClient().post("/api/auth/register/", body, format="json")
    assert r.status_code == 201
    assert User.objects.get(email="n@example.com").invited_by == user
    assert client_for(user).get("/api/gamification/profile/").data["invited"] == 1


def test_five_invites_give_the_badge(user):
    code = ensure_referral_code(user)
    for i in range(5):
        record_ref_code(User.objects.create_user(telegram_id=200 + i), code)
    assert UserAchievement.objects.filter(user=user, code="invited_5").exists()


def test_bot_start_ref_opens_app_with_code(settings):
    from aiogram.filters import CommandObject

    from telegram_bot import handlers

    settings.PUBLIC_URL = "https://y.example.com"
    sent = {}

    class Msg:
        from_user = None

        async def answer(self, text, reply_markup=None):
            sent["url"] = reply_markup.inline_keyboard[0][0].web_app.url

    from asgiref.sync import async_to_sync

    async_to_sync(handlers.cmd_start)(Msg(), CommandObject(command="start", args="ref_ab3k9mzq"))
    assert sent["url"] == "https://y.example.com/?ref=ab3k9mzq"


def test_public_config_has_app_short_name(settings):
    settings.TELEGRAM_APP_SHORT_NAME = "play"
    assert APIClient().get("/api/auth/telegram/config/").data["app_short_name"] == "play"


# --------------------------------------------------------------------------- images
@pytest.mark.parametrize("size", [(1080, 1920), (1080, 1080)])
def test_upload_exact_card_sizes(api, settings, size):
    settings.PUBLIC_URL = "https://y.example.com"
    r = api.post("/api/share/upload/", {"image": png(size)}, format="multipart")
    assert r.status_code == 201
    assert r.data["url"].startswith("https://y.example.com/media/shares/") and r.data["url"].endswith(".png")
    path = r.data["url"].split("/media/", 1)[1]
    assert StoredFile.objects.get(name=path).content_type == "image/png"
    assert APIClient().get(f"/media/{path}").status_code == 200  # Telegram fetches it without a login


def test_upload_rejects_wrong_size_and_non_png(api):
    assert api.post("/api/share/upload/", {"image": png((1000, 1000))}, format="multipart").data["detail"] == "bad_size"
    assert api.post("/api/share/upload/", {"image": png(fmt="JPEG")}, format="multipart").status_code == 400
    junk = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    assert api.post("/api/share/upload/", {"image": junk}, format="multipart").data["detail"] == "not_png"
    assert APIClient().post("/api/share/upload/", {"image": png()}, format="multipart").status_code == 401


@pytest.mark.parametrize(("fmt", "size"), [("story", (1080, 1920)), ("square", (1080, 1080))])
@pytest.mark.parametrize("theme", ["violet", "yellow", "dark"])
def test_server_fallback_renders_exact_size(api, fmt, size, theme):
    card = {
        "format": fmt,
        "theme": theme,
        "lang": "ru",
        "content": {
            "template": "streak",
            "emoji": "🔥",
            "kicker": "Серия дней · o‘zbekcha g'",
            "main": "🔥 30 дней",
            "stats": [{"label": "Лучшая", "value": "30 дн."}, {"label": "Цель", "value": "100 дн."}],
        },
        "name": "Азиз",
        "footer": "Учу слова с Yodflip",
        "link": "https://t.me/yodflip_bot/play?startapp=ref_ab3k9mzq",
    }
    r = api.post("/api/share/render/", card, format="json")
    assert r.status_code == 200 and r["Content-Type"] == "image/png"
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.format == "PNG" and im.size == size


def test_share_events_are_logged(api, user):
    assert api.post("/api/share/events/", {"template": "game", "platform": "story"}, format="json").status_code == 201
    assert api.post("/api/share/events/", {"template": "nope", "platform": "story"}, format="json").status_code == 400
    e = ShareEvent.objects.get()
    assert (e.user, e.template, e.platform) == (user, "game", "story")


def test_old_uploads_are_cleaned_up(api):
    api.post("/api/share/upload/", {"image": png()}, format="multipart")
    img = ShareImage.objects.get()
    assert cleanup()["due"] == 0
    ShareImage.objects.update(created_at=img.created_at - timedelta(hours=49))
    assert cleanup()["due"] == 1
    assert not ShareImage.objects.exists() and not StoredFile.objects.filter(name=img.file.name).exists()
