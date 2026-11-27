"""Classes (teacher mode): join, approval, limits, assignment progress, reminders, privacy, CSV, announcements."""

import csv
import io
import json
import time
from datetime import timedelta

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from broadcasts import services as bsvc
from broadcasts.models import Broadcast, BroadcastDelivery
from classes import reminders, services
from classes.models import Assignment, AssignmentReminder, Classroom, Membership, Organization
from decks.models import Card, Deck
from gamification.models import GameSession
from jobs.services import run_all
from telegram_auth.verify import sign_init_data
from words.models import Pack, UserLevelWord, UserWord, Word, WordTranslation

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-token-for-tests"


@pytest.fixture
def words(db):
    pack = Pack.objects.create(track="en", level="A1", slug="p", name_uz="p", name_en="p", name_ru="p")
    out = []
    for i in range(30):
        w = Word.objects.create(
            track="en",
            level="A1",
            pack=pack,
            word=f"word{i}",
            part_of_speech="noun",
            definition=f"def {i}",
            translation_uz=f"soz{i}",
        )
        for lang in ("uz", "ru", "de"):
            WordTranslation.objects.create(word=w, lang=lang, text=f"{lang}{i}")
        out.append(w)
    return out


@pytest.fixture
def teacher(db):
    return User.objects.create_user(email="t@example.com", password="secret123", display_name="Ustoz", telegram_id=500)


@pytest.fixture
def tapi(teacher, client_for):
    return client_for(teacher)


def student(n, **kw):
    return User.objects.create_user(
        email=f"s{n}@example.com", password="x12345678", display_name=f"Talaba{n}", telegram_id=1000 + n, **kw
    )


def make_class(tapi, **kw):
    r = tapi.post("/api/classes/", {"name": "7-A", "track": "en", **kw}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def join(client_for, u, code):
    return client_for(u).post(f"/api/classes/join/{code}/")


class FakeTelegram:
    def __init__(self):
        self.calls, self.fail = [], {}

    @property
    def chats(self):
        return [c.chat_id for c in self.calls]


@pytest.fixture
def tg(monkeypatch, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.PUBLIC_URL = "https://yodflip.example.com"
    api = FakeTelegram()

    async def fake_call(self, method, request_timeout=None):
        errors = api.fail.get(getattr(method, "chat_id", None))
        if errors:
            raise errors.pop(0)(method)
        api.calls.append(method)
        return True

    api.deadline_chats = lambda: [c.chat_id for c in api.calls if "⏰" in (getattr(c, "text", "") or "")]

    async def no_sleep(s):
        return None

    monkeypatch.setattr(Bot, "__call__", fake_call)
    monkeypatch.setattr(bsvc, "sleep", no_sleep)
    monkeypatch.setattr(bsvc, "spawn", lambda pk, token: bsvc.run(pk, token))
    from telegram_bot import notify

    monkeypatch.setattr(notify, "sleep", no_sleep)
    return api


# --------------------------------------------------------------------------- create / join
def test_create_class_with_codes_and_links(tapi, settings):
    settings.TELEGRAM_BOT_USERNAME = "yodflip_bot"
    settings.TELEGRAM_APP_SHORT_NAME = "app"
    settings.PUBLIC_URL = "https://y.example.com"
    c = make_class(tapi, level="A2", description="Kechki guruh", color="#00B894")
    code = c["join_code"]
    assert len(code) == 6 and code.isalnum() and code.isupper()
    assert c["links"]["telegram"] == f"https://t.me/yodflip_bot/app?startapp=class_{code}"
    assert c["links"]["web"] == f"https://y.example.com/join/{code}"
    assert c["role"] == "teacher" and c["is_owner"]
    assert services.code_from_param(f"class_{code}") == code
    assert services.code_from_param("class_../xx") == services.code_from_param("duel_ABCDEF") == ""


def test_join_by_code_and_web_link(tapi, client_for, words):
    c = make_class(tapi)
    s1 = student(1)
    preview = client_for(s1).get(f"/api/classes/join/{c['join_code'].lower()}/")
    assert preview.status_code == 200
    assert preview.data["name"] == "7-A" and preview.data["membership"] is None
    assert "email" not in preview.data["teacher"]
    r = join(client_for, s1, c["join_code"])
    assert r.data == {"id": c["id"], "membership": "active"}
    assert join(client_for, s1, c["join_code"]).data["membership"] == "active"  # idempotent
    assert Membership.objects.filter(classroom_id=c["id"]).count() == 1
    mine = client_for(s1).get("/api/classes/").data["classes"]
    assert [x["role"] for x in mine] == ["student"]
    assert client_for(s1).get("/api/classes/join/ZZZZZZ/").status_code == 404


def test_new_telegram_user_joins_through_startapp(tapi, settings, words):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    c = make_class(tapi)
    pairs = {
        "user": json.dumps({"id": 777, "first_name": "Yangi"}),
        "auth_date": str(int(time.time())),
        "start_param": f"class_{c['join_code']}",
    }
    r = APIClient().post("/api/auth/telegram/webapp/", {"init_data": sign_init_data(pairs, TOKEN)}, format="json")
    assert r.status_code == 200
    new = User.objects.get(telegram_id=777)  # registered instantly
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert client.get(f"/api/classes/join/{c['join_code']}/").data["membership"] is None  # confirm screen first
    assert client.post(f"/api/classes/join/{c['join_code']}/").data["membership"] == "active"
    assert Membership.objects.get(user=new).status == "active"


def test_approval_mode_remove_and_rejoin_rules(tapi, client_for):
    c = make_class(tapi, approval_required=True)
    s1, s2 = student(1), student(2)
    assert join(client_for, s1, c["join_code"]).data["membership"] == "pending"
    assert client_for(s1).get(f"/api/classes/{c['id']}/").data["assignments"] == []
    assert tapi.post(f"/api/classes/{c['id']}/members/{s1.id}/approve/").status_code == 200
    assert Membership.objects.get(user=s1).status == "active"
    join(client_for, s2, c["join_code"])
    assert tapi.post(f"/api/classes/{c['id']}/members/{s2.id}/remove/").status_code == 200
    assert join(client_for, s2, c["join_code"]).status_code == 403  # removed students can't rejoin by code
    # a student leaves and may come back
    assert client_for(s1).post(f"/api/classes/{c['id']}/leave/").status_code == 200
    assert Membership.objects.get(user=s1).status == "left"
    assert join(client_for, s1, c["join_code"]).data["membership"] == "pending"


def test_regenerate_code_invalidates_old_one(tapi, client_for):
    c = make_class(tapi)
    new = tapi.post(f"/api/classes/{c['id']}/regenerate/").data["join_code"]
    assert new != c["join_code"]
    assert join(client_for, student(1), c["join_code"]).status_code == 404
    assert join(client_for, student(2), new).status_code == 200


def test_free_limits_classes_and_students(tapi, client_for, settings):
    settings.CLASS_LIMITS = {"free": {"classes": 2, "students": 3}, "pro": {"classes": 9, "students": 9}}
    a = make_class(tapi)
    make_class(tapi)
    r = tapi.post("/api/classes/", {"name": "3", "track": "de"}, format="json")
    assert r.status_code == 400 and r.data["detail"] == "class_limit"
    tapi.patch(f"/api/classes/{a['id']}/", {"archived": True}, format="json")
    make_class(tapi)  # archived classes don't count
    b = Classroom.objects.exclude(pk=a["id"]).first()
    for i in range(3):
        assert join(client_for, student(i), b.join_code).status_code == 200
    r = join(client_for, student(9), b.join_code)
    assert r.status_code == 400 and r.data["detail"] == "class_full"
    # archived classes can't be joined
    assert join(client_for, student(10), a["join_code"]).status_code == 404


def test_org_plan_overrides_limits(teacher, tapi, settings):
    settings.CLASS_LIMITS = {"free": {"classes": 1, "students": 3}, "pro": {"classes": 5, "students": 100}}
    org = Organization.objects.create(name="Markaz", plan="pro")
    org.teachers.add(teacher)
    for _ in range(3):
        c = make_class(tapi, org=org.id)
    assert c["plan"] == "pro" and c["limits"]["students"] == 100
    boss = User.objects.create_user(email="boss@example.com", password="x12345678")
    org.admins.add(boss)
    seen = APIClient()
    seen.force_authenticate(boss)
    assert len(seen.get("/api/classes/").data["classes"]) == 3  # the org admin sees all its classes
    assert seen.get(f"/api/classes/{c['id']}/").data["class"]["role"] == "teacher"


def test_co_teacher_invite(tapi, client_for):
    c = make_class(tapi)
    helper = student(5)
    code = Classroom.objects.get(pk=c["id"]).teacher_code
    assert client_for(helper).post(f"/api/classes/teach/{code}/").status_code == 200
    d = client_for(helper).get(f"/api/classes/{c['id']}/").data
    assert d["class"]["role"] == "teacher" and not d["class"]["is_owner"]
    assert "teacher" not in d["class"]["links"]  # only the owner can invite more teachers
    assert client_for(helper).post(f"/api/classes/{c['id']}/regenerate/").status_code == 403


# --------------------------------------------------------------------------- assignments
def level_assignment(tapi, cid, **kw):
    body = {
        "kind": "level",
        "level": "A1",
        "lesson_from": 1,
        "lesson_to": 1,
        "target_kind": "learn_pct",
        "target_value": 50,
        "due_at": (timezone.now() + timedelta(days=3)).isoformat(),
        **kw,
    }
    r = tapi.post(f"/api/classes/{cid}/assignments/", body, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_assignment_progress_uses_existing_learned_data_without_double_counting(tapi, client_for, words):
    c = make_class(tapi)
    s1 = student(1)
    join(client_for, s1, c["join_code"])
    a = level_assignment(tapi, c["id"])
    assert a["word_count"] == 20  # lesson 1 = the first 20 words in theme order
    now = timezone.now()
    # w0: found in the level AND learned (box 5) in the lists → counted once
    UserLevelWord.objects.create(user=s1, word=words[0], track="en", level="A1", found_at=now)
    UserWord.objects.create(user=s1, track="en", term_key="word0", term="word0", word=words[0], box=5)
    # w1: learned through a deck (same normalised term, no word link)
    UserWord.objects.create(user=s1, track="en", term_key="word1", term="Word1", box=5)
    # w2: seen but not learned; w25: learned but outside lesson 1
    UserWord.objects.create(user=s1, track="en", term_key="word2", term="word2", box=3)
    UserLevelWord.objects.create(user=s1, word=words[25], track="en", level="A1", found_at=now)
    p = client_for(s1).get(f"/api/classes/{c['id']}/").data["assignments"][0]["progress"]
    assert (p["done"], p["total"], p["percent"], p["status"]) == (2, 20, 10, "pending")
    # The teacher table shows the same numbers.
    row = tapi.get(f"/api/classes/{c['id']}/").data["students"][0]
    assert row["assignments"][str(a["id"])]["done"] == 2
    assert "email" not in row and "telegram_id" not in row


def test_playing_an_assignment_counts_found_words_and_plays(tapi, client_for, words):
    c = make_class(tapi)
    s1 = student(1)
    join(client_for, s1, c["join_code"])
    a = level_assignment(tapi, c["id"], target_kind="plays", target_value=2)
    sapi = client_for(s1)
    r = sapi.get("/api/games/words/", {"game": "speed", "track": "en", "source": "assignment", "id": a["id"]})
    assert r.status_code == 200
    ids = {i["word_id"] for i in r.data["items"]}
    assert ids == {w.id for w in words[:20]}
    results = [{"term": w.word, "word_id": w.id, "correct": True} for w in words[:10]]
    body = {"game": "speed", "track": "en", "source": "assignment", "results": results, "assignment_id": a["id"]}
    assert sapi.post("/api/games/results/", body, format="json").status_code == 200
    assert UserLevelWord.objects.filter(user=s1, found_at__isnull=False).count() == 10
    p = sapi.get(f"/api/classes/{c['id']}/").data["assignments"][0]["progress"]
    assert (p["done"], p["plays"], p["status"]) == (10, 1, "pending")
    # the same words again: no double counting, but a second play
    sapi.post("/api/games/results/", body, format="json")
    p = sapi.get(f"/api/classes/{c['id']}/").data["assignments"][0]["progress"]
    assert (p["done"], p["plays"], p["status"]) == (10, 2, "done")
    # next round serves only the words that are still unlearned
    r = sapi.get("/api/games/words/", {"game": "speed", "track": "en", "source": "assignment", "id": a["id"]})
    assert {i["word_id"] for i in r.data["items"]} == {w.id for w in words[10:20]}
    # outsiders can neither play nor report it
    out = client_for(student(9))
    assert out.get("/api/games/words/", {"game": "speed", "source": "assignment", "id": a["id"]}).status_code == 404
    assert out.post("/api/games/results/", body, format="json").status_code == 404


def test_overdue_status_and_deck_assignment(tapi, teacher, client_for, words):
    c = make_class(tapi)
    s1 = student(1)
    join(client_for, s1, c["join_code"])
    deck = Deck.objects.create(owner=teacher, name="Mening", track="en")
    Card.objects.create(deck=deck, term="apple", translation="olma")
    Card.objects.create(deck=deck, term="pear", translation="nok")
    r = tapi.post(
        f"/api/classes/{c['id']}/assignments/",
        {
            "kind": "deck",
            "deck": deck.id,
            "target_value": 50,
            "due_at": (timezone.now() + timedelta(days=1)).isoformat(),
        },
        format="json",
    )
    assert r.status_code == 201 and r.data["start"] == {"source": "deck", "id": deck.id, "assignment": r.data["id"]}
    # the deck is private, but assigned: the student may play it
    sapi = client_for(s1)
    assert (
        sapi.get("/api/games/words/", {"game": "speed", "track": "en", "source": "deck", "id": deck.id}).status_code
        == 200
    )
    assert (
        client_for(student(2)).get("/api/games/words/", {"game": "speed", "source": "deck", "id": deck.id}).status_code
        == 403
    )
    UserWord.objects.create(user=s1, track="en", term_key="apple", term="apple", box=5)
    p = sapi.get(f"/api/classes/{c['id']}/").data["assignments"][0]["progress"]
    assert (p["done"], p["total"], p["status"]) == (1, 2, "done")
    Assignment.objects.update(due_at=timezone.now() - timedelta(hours=1))
    UserWord.objects.all().delete()
    p = sapi.get(f"/api/classes/{c['id']}/").data["assignments"][0]["progress"]
    assert p["status"] == "overdue"


# --------------------------------------------------------------------------- reminders
def test_deadline_reminder_once_and_only_for_unfinished(tapi, client_for, words, tg):
    c = make_class(tapi)
    s1, s2, s3 = student(1), student(2), student(3, notify_classes=False)
    for s in (s1, s2, s3):
        join(client_for, s, c["join_code"])
    a = level_assignment(tapi, c["id"], due_at=(timezone.now() + timedelta(hours=10)).isoformat(), target_value=5)
    level_assignment(tapi, c["id"], due_at=(timezone.now() + timedelta(days=3)).isoformat())  # not due yet
    for w in words[:20]:  # s2 has finished
        UserLevelWord.objects.create(user=s2, word=w, track="en", level="A1", found_at=timezone.now())
    stats = reminders.send_due()
    assert tg.chats == [s1.telegram_id]
    assert stats["sent"] == 1 and stats["skipped"]["completed"] == 1 and stats["skipped"]["notifications_off"] == 1
    assert "A1" in tg.calls[0].text
    reminders.send_due()
    run_all("cron")  # (the daily quiz may go out too: only deadline messages are counted)
    assert tg.deadline_chats() == [s1.telegram_id]  # idempotent across runs
    assert AssignmentReminder.objects.filter(assignment_id=a["id"]).count() == 1


def test_deadline_reminder_released_when_not_delivered(tapi, client_for, words, tg, monkeypatch):
    c = make_class(tapi)
    s1 = student(1)
    join(client_for, s1, c["join_code"])
    level_assignment(tapi, c["id"], due_at=(timezone.now() + timedelta(hours=5)).isoformat())
    tg.fail[s1.telegram_id] = [lambda m: TelegramRetryAfter(method=m, message="flood", retry_after=999)]
    reminders.send_due(budget=1)
    assert tg.chats == [] and not AssignmentReminder.objects.exists()  # given back: certainly not delivered
    reminders.send_due()
    assert tg.chats == [s1.telegram_id]


# --------------------------------------------------------------------------- privacy, dashboard
def test_teacher_sees_only_their_own_class(tapi, client_for, words):
    c = make_class(tapi)
    s1 = student(1)
    join(client_for, s1, c["join_code"])
    other_teacher = student(50)
    other = client_for(other_teacher)
    other_class = other.post("/api/classes/", {"name": "B", "track": "en"}, format="json").data
    s2 = student(2)
    join(client_for, s2, other_class["join_code"])
    for url in (
        f"/api/classes/{c['id']}/students/{s1.id}/",
        f"/api/classes/{c['id']}/export.csv",
        f"/api/classes/{c['id']}/hardest/",
        f"/api/classes/{c['id']}/leaderboard/",
    ):
        assert other.get(url).status_code == 404
    assert other.get(f"/api/classes/{c['id']}/").status_code == 404
    assert other.post(f"/api/classes/{c['id']}/announce/", {"text": "hi"}, format="json").status_code == 404
    assert other.post(f"/api/classes/{c['id']}/members/{s1.id}/remove/").status_code == 404
    # a teacher can't open a student who isn't in their class
    assert tapi.get(f"/api/classes/{c['id']}/students/{s2.id}/").status_code == 404
    # students see classmates only on the leaderboard (name + avatar), never the teacher table
    d = client_for(s1).get(f"/api/classes/{c['id']}/").data
    assert "students" not in d and "join_code" not in d["class"]
    assert set(d["leaderboard"][0]) == {"rank", "id", "name", "avatar_url", "xp", "is_me"}
    detail = tapi.get(f"/api/classes/{c['id']}/students/{s1.id}/").data
    assert detail["student"]["name"] == "Talaba1"
    assert "s1@example.com" not in json.dumps(detail)


def test_dashboard_overview_hardest_words_and_deck(tapi, teacher, client_for, words):
    c = make_class(tapi)
    s1, s2 = student(1), student(2)
    for s in (s1, s2):
        join(client_for, s, c["join_code"])
    for s in (s1, s2):
        UserWord.objects.create(user=s, track="en", term_key="word3", term="word3", word=words[3], miss_count=2)
    UserWord.objects.create(user=s1, track="en", term_key="hard", term="hard", translation_uz="qattiq", miss_count=5)
    hard = tapi.get(f"/api/classes/{c['id']}/hardest/").data["words"]
    assert [h["term"] for h in hard] == ["word3", "hard"]
    assert hard[0]["students"] == 2 and hard[0]["translation"] == "soz3"
    r = tapi.post(f"/api/classes/{c['id']}/hardest/", {}, format="json")
    assert r.status_code == 201 and r.data["kind"] == "deck" and r.data["word_count"] == 2
    deck = Deck.objects.get(pk=r.data["deck"])
    assert deck.owner == teacher and not deck.is_public
    d = tapi.get(f"/api/classes/{c['id']}/").data
    assert d["overview"]["students"] == 2 and d["overview"]["assignments"] == 1
    GameSession.objects.create(user=s1, track="en", game="speed", xp=40)
    from gamification.services import record_activity

    record_activity(s1, 40, 4, 5)
    board = tapi.get(f"/api/classes/{c['id']}/leaderboard/").data["entries"]
    assert board[0]["name"] == "Talaba1" and board[0]["xp"] == 40


def test_csv_export(tapi, client_for, words):
    c = make_class(tapi, name="Kechki 'A'")
    s1 = student(1)
    join(client_for, s1, c["join_code"])
    a = level_assignment(tapi, c["id"], title="Birinchi dars")
    UserLevelWord.objects.create(user=s1, word=words[0], track="en", level="A1", found_at=timezone.now())
    r = tapi.get(f"/api/classes/{c['id']}/export.csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    body = r.content.decode("utf-8")
    assert body.startswith("﻿")
    rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
    assert rows[0][0] == "Ism" and "Birinchi dars (%)" in rows[0]
    assert rows[1][0] == "Talaba1"
    assert rows[1][rows[0].index("Birinchi dars (%)")] == "5"  # 1 of 20 words
    assert rows[1][rows[0].index("Birinchi dars (holat)")] == "pending"
    assert "s1@example.com" not in body
    assert a["id"]


def test_announcement_goes_through_the_broadcast_sender(tapi, client_for, tg, words):
    c = make_class(tapi)
    s1, s2, s3 = student(1), student(2), student(3)
    join(client_for, s1, c["join_code"])
    join(client_for, s2, c["join_code"])
    tapi.post(f"/api/classes/{c['id']}/members/{s2.id}/remove/")
    outsider = student(4)
    assert outsider and s3
    r = tapi.post(f"/api/classes/{c['id']}/announce/", {"text": "Ertaga <test> bor!"}, format="json")
    assert r.status_code == 201 and r.data["recipients"] == 1
    b = Broadcast.objects.get()
    assert b.audience == "class" and b.audience_ref == str(c["id"]) and b.webapp_path == f"/classes/{c['id']}"
    assert b.status == Broadcast.DONE
    assert list(BroadcastDelivery.objects.values_list("user_id", flat=True)) == [s1.id]
    assert tg.chats == [s1.telegram_id]
    assert "Ertaga &lt;test&gt; bor!" in tg.calls[0].text and "7-A" in tg.calls[0].text
    btn = tg.calls[0].reply_markup.inline_keyboard[0][0]
    assert btn.web_app.url == f"https://yodflip.example.com/classes/{c['id']}"
    # the admin broadcast form doesn't offer the class audience
    from broadcasts.models import AUDIENCES

    assert "class" not in dict(AUDIENCES)
