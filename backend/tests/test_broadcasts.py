"""Admin broadcast: audience, test send, pacing, 429 / 403, resume without duplicates, schedule, placeholders."""

import io
import uuid
from datetime import timedelta

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramUnauthorizedError
from aiogram.methods import SendMessage, SendPhoto
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image

from accounts.models import User
from botquiz.models import QuizSettings
from broadcasts import services
from broadcasts.content import check_html, render
from broadcasts.models import Broadcast, BroadcastDelivery
from core.models import StoredFile
from jobs import locks
from jobs.services import run_all
from words.models import UserWord

pytestmark = pytest.mark.django_db
D = BroadcastDelivery


class Killed(BaseException):
    """The process dies (not an Exception, so nothing catches it)."""


class Telegram:
    def __init__(self):
        self.calls, self.fail, self.hook = [], {}, None

    @property
    def chats(self):
        return [c.chat_id for c in self.calls]


@pytest.fixture(autouse=True)
def setup(settings, monkeypatch):
    settings.TELEGRAM_BOT_TOKEN = "123456:TEST-token-for-tests"
    settings.PUBLIC_URL = "https://yodflip.example.com"
    settings.NAPS = []
    settings.SPAWN = True

    async def no_sleep(s):
        settings.NAPS.append(s)

    monkeypatch.setattr(services, "sleep", no_sleep)
    # Run "in the background" = right here.
    monkeypatch.setattr(services, "spawn", lambda pk, token: services.run(pk, token) if settings.SPAWN else None)
    return settings


@pytest.fixture
def tg(monkeypatch):
    api = Telegram()

    async def fake_call(self, method, request_timeout=None):
        errors = api.fail.get(method.chat_id)
        if errors:
            raise errors.pop(0)(method)
        api.calls.append(method)
        if api.hook:
            api.hook()
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    return api


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@example.com", password="x12345678", telegram_id=999, is_staff=True, display_name="Boss"
    )


@pytest.fixture
def admin(admin_user):
    c = Client()
    c.force_login(admin_user)
    return c


def people(n=3, **kw):
    return [User.objects.create_user(telegram_id=i, display_name=f"U{i}", **kw) for i in range(1, n + 1)]


def form(**kw):
    return {"text": "Salom", "audience": "all", "nonce": str(uuid.uuid4()), "action": "send", **kw}


def png(size=(20, 20), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, fmt)
    return SimpleUploadedFile("p.png", buf.getvalue(), content_type="image/png")


# --- access ---------------------------------------------------------------------------------
def test_staff_only(admin, user):
    urls = ["", "count/?audience=all", "history/"]
    c = Client()
    c.force_login(user)
    for client in (Client(), c):
        for u in urls:
            assert client.get(f"/admin/broadcast/{u}").status_code == 302
        assert client.post("/admin/broadcast/submit/", form()).status_code == 302
    assert not Broadcast.objects.exists()
    html = admin.get("/admin/broadcast/").content.decode()
    assert "Menga test yuborish" in html and "Kunlik eslatma" in html
    assert admin.get("/admin/broadcasts/broadcast/").url == "/admin/broadcast/"
    assert "Xabar yuborish" in admin.get("/admin/").content.decode()


def test_csrf_is_enforced(admin_user):
    c = Client(enforce_csrf_checks=True)
    c.force_login(admin_user)
    assert c.post("/admin/broadcast/submit/", form()).status_code == 403


# --- audience -------------------------------------------------------------------------------
def test_audience_counts(admin, admin_user):
    day = timezone.localdate()
    admin_user.telegram_id = None
    admin_user.save()
    old = timezone.now() - timedelta(days=30)
    rows = [
        {"active_track": "en", "last_active_date": day},
        {"active_track": "de", "last_active_date": day - timedelta(days=2)},
        {"active_track": "de", "last_active_date": day - timedelta(days=3), "email": "web@example.com"},
        {"active_track": "en", "last_active_date": day - timedelta(days=6)},
        {"active_track": "en", "last_active_date": day - timedelta(days=7)},
        {"active_track": "en", "date_joined": old},  # never played
        {"active_track": "en"},  # joined today, never played
    ]
    for n, kw in enumerate(rows):
        User.objects.create_user(telegram_id=n + 1, **kw)
    User.objects.create_user(telegram_id=50, is_active=False)
    QuizSettings.objects.create(user=User.objects.create_user(telegram_id=51), bot_blocked=True)
    User.objects.create_user(email="no-telegram@example.com")
    expected = {"all": 7, "en": 5, "de": 2, "active7": 4, "inactive3": 4, "not_today": 6, "web": 1}
    for key, n in expected.items():
        assert admin.get(f"/admin/broadcast/count/?audience={key}").json()["count"] == n, key
    assert admin.get("/admin/broadcast/count/?audience=x").status_code == 400


# --- test send ------------------------------------------------------------------------------
def test_test_send_goes_only_to_the_admin(admin, admin_user, tg):
    people()
    r = admin.post("/admin/broadcast/submit/", form(action="test", text="Salom <b>{name}</b>"))
    assert r.json() == {"ok": True}
    assert tg.chats == [999] and tg.calls[0].text == "Salom <b>Boss</b>" and tg.calls[0].parse_mode == "HTML"
    r = admin.post("/admin/broadcast/submit/", form(action="test", photo=png()))
    assert r.json()["ok"] and isinstance(tg.calls[1], SendPhoto) and tg.chats == [999, 999]
    assert not Broadcast.objects.exists() and not StoredFile.objects.exists()


def test_test_send_errors(admin, admin_user, tg):
    tg.fail[999] = [lambda m: TelegramForbiddenError(method=m, message="bot was blocked by the user")]
    r = admin.post("/admin/broadcast/submit/", form(action="test"))
    assert r.status_code == 502 and "/start" in r.json()["error"]
    admin_user.telegram_id = None
    admin_user.save()
    assert "Telegram ulanmagan" in admin.post("/admin/broadcast/submit/", form(action="test")).json()["error"]


# --- sending --------------------------------------------------------------------------------
def test_send_to_all(admin, admin_user, tg, setup):
    people(3)
    r = admin.post(
        "/admin/broadcast/submit/",
        form(text="Salom {name}", button_kind="webapp", button_text="Ochish"),
    ).json()
    assert r["ok"] and r["started"]
    assert sorted(tg.chats) == [1, 2, 3, 999]
    assert {c.text for c in tg.calls} == {"Salom U1", "Salom U2", "Salom U3", "Salom Boss"}
    assert tg.calls[0].reply_markup.inline_keyboard[0][0].web_app.url == "https://yodflip.example.com/"
    b = Broadcast.objects.get()
    assert (b.status, b.total, b.sent, b.failed, b.created_by) == ("done", 4, 4, 0, admin_user)
    assert b.started_at and b.finished_at
    item = admin.get("/admin/broadcast/history/").json()["items"][0]
    assert (item["sent"], item["total"], item["status"], item["can_resume"]) == (4, 4, "done", False)
    assert locks.holder(services.LOCK) == ""


def test_double_submit_sends_once(admin, tg):
    data = form()
    admin.post("/admin/broadcast/submit/", data)
    assert admin.post("/admin/broadcast/submit/", data).json()["duplicate"] is True
    assert tg.chats == [999] and Broadcast.objects.count() == 1


def test_url_button_and_photo_is_uploaded_once(admin, tg):
    people(2)
    r = admin.post(
        "/admin/broadcast/submit/",
        form(photo=png(), button_kind="url", button_text="Sayt", button_url="https://example.com/x"),
    )
    assert r.json()["ok"], r.content
    assert all(isinstance(c, SendPhoto) and c.caption == "Salom" for c in tg.calls) and len(tg.calls) == 3
    assert tg.calls[0].reply_markup.inline_keyboard[0][0].url == "https://example.com/x"


def test_photo_file_id_is_reused(tg, monkeypatch):
    class Sent:
        photo = [type("P", (), {"file_id": "small"}), type("P", (), {"file_id": "big"})]

    photos = []

    async def fake_call(self, method, request_timeout=None):
        photos.append(method.photo)
        return Sent

    monkeypatch.setattr(Bot, "__call__", fake_call)
    people(3)
    b = Broadcast.objects.create(text="x", photo=png())
    assert services.start(b.pk)
    assert photos[1:] == ["big", "big"] and photos[0] != "big"
    b.refresh_from_db()
    assert b.photo_file_id == "big"


def test_batches_and_pace(tg, setup, monkeypatch):
    monkeypatch.setattr(services, "BATCH", 4)
    sizes = []
    original = services.next_batch
    monkeypatch.setattr(services, "next_batch", lambda pk: (sizes.append(len(rows := original(pk))), rows)[1])
    people(10)
    services.start(Broadcast.objects.create(text="x").pk)
    assert sizes == [4, 4, 2, 0]
    assert len(tg.calls) == 10 and setup.NAPS == [1 / 25] * 10  # at most 25 per second


def test_429_waits_retry_after_and_keeps_the_lock(tg, setup):
    people(2)
    tg.fail[1] = [lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=25)]
    b = Broadcast.objects.create(text="x")
    services.start(b.pk)
    assert setup.NAPS[:3] == [10, 10, 5]  # 25 s, with a heartbeat in between
    assert sorted(tg.chats) == [1, 2]
    b.refresh_from_db()
    assert (b.status, b.sent, b.failed) == ("done", 2, 0)


def test_endless_429_pauses_and_can_be_resumed(admin, tg):
    people(2)
    tg.fail[1] = [lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=1)] * 4
    b = Broadcast.objects.create(text="x", audience="en")
    User.objects.filter(telegram_id=999).update(active_track="de")
    services.start(b.pk)
    b.refresh_from_db()
    assert b.status == "paused" and "429" in b.error and tg.chats == []
    assert admin.post(f"/admin/broadcast/{b.pk}/resume/").json()["ok"]
    assert sorted(tg.chats) == [1, 2]
    b.refresh_from_db()
    assert (b.status, b.error) == ("done", "")


def test_403_marks_the_user_inactive_for_the_bot(tg):
    people(3)
    tg.fail[2] = [lambda m: TelegramForbiddenError(method=m, message="bot was blocked by the user")]
    b = Broadcast.objects.create(text="x")
    services.start(b.pk)
    b.refresh_from_db()
    assert (b.status, b.sent, b.failed) == ("done", 2, 1)
    u = User.objects.get(telegram_id=2)
    assert u.quiz_settings.bot_blocked is True and u.is_active is True  # may still log in
    assert D.objects.get(user=u).status == D.BLOCKED
    assert services.audience("all").count() == 2


def test_other_errors_are_counted_and_never_retried(tg):
    people(3)
    tg.fail[2] = [lambda m: RuntimeError("timeout")]
    b = Broadcast.objects.create(text="x")
    services.start(b.pk)
    b.refresh_from_db()
    assert (b.status, b.sent, b.failed) == ("done", 2, 1) and tg.chats == [1, 3]


def test_wrong_token_pauses_without_losing_anybody(tg):
    people(2)
    tg.fail[1] = [lambda m: TelegramUnauthorizedError(method=m, message="Unauthorized")]
    b = Broadcast.objects.create(text="x")
    services.start(b.pk)
    b.refresh_from_db()
    assert b.status == "paused" and D.objects.filter(status=D.PENDING).count() == 2


# --- resume ---------------------------------------------------------------------------------
def test_resume_after_a_restart_never_sends_twice(admin, tg):
    people(6)
    User.objects.filter(telegram_id=999).update(telegram_id=None)
    b = Broadcast.objects.create(text="x")

    def die_after_three():
        if len(tg.calls) == 3:
            raise Killed  # Telegram has delivered the third one, the process dies before it is noted

    tg.hook = die_after_three
    token = services.take(b.pk)
    with pytest.raises(Killed):
        services.run(b.pk, token)
    tg.hook = None
    locks.JobLock.objects.update(token=token, locked_until=timezone.now() + timedelta(seconds=60))  # a real kill
    b.refresh_from_db()
    assert b.status == "running"
    assert not admin.get("/admin/broadcast/history/").json()["items"][0]["can_resume"]  # may still be alive
    assert admin.post(f"/admin/broadcast/{b.pk}/resume/").status_code == 409
    locks.JobLock.objects.update(locked_until=timezone.now() - timedelta(seconds=1))
    item = admin.get("/admin/broadcast/history/").json()["items"][0]
    assert item["status"] == "stalled" and item["can_resume"]

    User.objects.create_user(telegram_id=77)  # joined later: not a recipient of this broadcast
    assert admin.post(f"/admin/broadcast/{b.pk}/resume/").json()["ok"]
    assert tg.chats == [1, 2, 3, 4, 5, 6]
    b.refresh_from_db()
    assert (b.status, b.total, b.sent, b.failed) == ("done", 6, 5, 1)  # the unsure one is not sent again
    assert admin.post(f"/admin/broadcast/{b.pk}/resume/").status_code == 409
    assert len(tg.chats) == 6


def test_pause_resume_cancel(admin, tg, monkeypatch):
    monkeypatch.setattr(services, "HEARTBEAT", -1)
    people(5)
    User.objects.filter(telegram_id=999).update(telegram_id=None)
    b = Broadcast.objects.create(text="x")
    stops = {2: "paused", 4: "cancelled"}
    hook = lambda: len(tg.calls) in stops and Broadcast.objects.update(status=stops[len(tg.calls)])  # noqa: E731
    original = services.finish_row

    def finish(row, out):
        original(row, out)
        hook()

    monkeypatch.setattr(services, "finish_row", finish)
    services.start(b.pk)
    assert tg.chats == [1, 2]
    assert admin.post(f"/admin/broadcast/{b.pk}/resume/").json()["ok"]
    assert tg.chats == [1, 2, 3, 4]
    assert admin.post(f"/admin/broadcast/{b.pk}/resume/").status_code == 409  # cancelled
    b.refresh_from_db()
    assert (b.status, b.sent) == ("cancelled", 4)


def test_only_one_broadcast_runs_at_a_time(admin, tg, setup):
    people(1)
    a, b = Broadcast.objects.create(text="a"), Broadcast.objects.create(text="b")
    token = services.take(a.pk)
    assert services.start(b.pk) is False
    assert admin.post("/admin/broadcast/submit/", form()).json()["started"] is False  # queued
    assert services.take(a.pk) is None
    services.run(a.pk, token)
    assert run_all()["broadcasts"]["due"] == 2  # the cron picks up the queue, one by one
    assert run_all()["broadcasts"]["due"] == 1
    assert not Broadcast.objects.exclude(status="done").exists()


def test_row_is_claimed_once(tg):
    people(1)
    b = Broadcast.objects.create(text="x")
    services.prepare(b.pk)
    services.prepare(b.pk)
    row = D.objects.select_related("user").get()
    assert services.claim(row, "x") == "x"
    assert services.claim(row, "x") is None


# --- schedule -------------------------------------------------------------------------------
def test_schedule(admin, tg, monkeypatch):
    when = timezone.localtime() + timedelta(hours=2)
    r = admin.post("/admin/broadcast/submit/", form(action="schedule", scheduled_at=when.strftime("%Y-%m-%dT%H:%M")))
    assert r.json()["ok"], r.content
    b = Broadcast.objects.get()
    assert b.status == "scheduled" and abs(b.scheduled_at - when) < timedelta(minutes=1)
    assert run_all()["broadcasts"]["due"] == 0 and tg.chats == []
    monkeypatch.setattr("django.utils.timezone.now", lambda: b.scheduled_at + timedelta(minutes=1))
    User.objects.filter(pk=b.created_by_id).update(is_active=True)
    assert run_all("scheduler")["broadcasts"]["due"] == 1
    run_all()
    assert tg.chats.count(999) >= 1 and sum(c.text == "Salom" for c in tg.calls) == 1


def test_schedule_in_the_past_and_cancel(admin, tg):
    r = admin.post("/admin/broadcast/submit/", form(action="schedule", scheduled_at="2020-01-01T10:00"))
    assert r.status_code == 400 and not Broadcast.objects.exists()
    b = Broadcast.objects.create(text="x", status="scheduled", scheduled_at=timezone.now() - timedelta(hours=1))
    assert admin.post(f"/admin/broadcast/{b.pk}/cancel/").json()["ok"]
    assert run_all()["broadcasts"]["due"] == 0 and tg.chats == []


# --- content --------------------------------------------------------------------------------
def test_placeholders(user):
    now, day = timezone.now(), timezone.localdate()
    user.display_name, user.streak, user.last_active_date = "Ali <b> & {streak}", 7, day
    UserWord.objects.create(user=user, track="en", term_key="a", seen=True, due_at=now - timedelta(hours=1))
    UserWord.objects.create(user=user, track="en", term_key="b", seen=True, due_at=now + timedelta(hours=1))
    assert render("{name}|{streak}|{due_words}|{x}", user) == "Ali &lt;b&gt; &amp; {streak}|7|1|{x}"
    user.last_active_date = day - timedelta(days=2)  # the streak is over
    user.display_name = " "
    assert render("{name} {streak}", user) == "do&#x27;stim 0"  # Telegram decodes it
    user.last_active_date = day - timedelta(days=1)
    assert render("{streak}", user) == "7"


@pytest.mark.parametrize(
    "text",
    [
        "Oddiy matn & 5 > 3",
        '<b>A <i>b</i></b> <a href="https://x.uz/?a=1&b=2">link</a> &lt;3',
        "<tg-spoiler>x</tg-spoiler> <code>y</code>",
        "x" * 4096,
    ],
)
def test_valid_html(text):
    assert check_html(text) == ""


@pytest.mark.parametrize(
    "text",
    [
        "<b>x",
        "<b><i>x</b></i>",
        "<script>x</script>",
        "a <br> b",
        "2 < 3",
        "x <b",
        '<a href="javascript:alert(1)">x</a>',
        "<a>x</a>",
        '<b onclick="x">x</b>',
        "<!-- x -->y",
        "<b> </b>",
        "x" * 4097,
        "x" * 4090 + "{name}",
    ],
)
def test_invalid_html(text):
    assert check_html(text)


def test_caption_limit_and_form_errors(admin, tg):
    assert check_html("x" * 1025, with_photo=True) and not check_html("x" * 1024, with_photo=True)
    bad = [
        form(text=""),
        form(text="<b>x"),
        form(audience="nobody"),
        form(button_kind="url", button_text="x"),
        form(button_kind="url", button_text="x", button_url="javascript:alert(1)"),
        form(button_kind="webapp"),
        form(photo=SimpleUploadedFile("p.png", b"not an image", content_type="image/png")),
        form(photo=png(fmt="GIF")),
        form(text="x" * 1025, photo=png()),
        form(action="other"),
        form(audience="de"),  # nobody
    ]
    for data in bad:
        r = admin.post("/admin/broadcast/submit/", data)
        assert r.status_code == 400 and r.json()["error"], data
    assert not Broadcast.objects.exists() and tg.chats == []


def test_crlf_is_normalised(admin, tg):
    admin.post("/admin/broadcast/submit/", form(text="a\r\nb"))
    assert tg.calls[0].text == "a\nb" and isinstance(tg.calls[0], SendMessage)
