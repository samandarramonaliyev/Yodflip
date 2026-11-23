"""Friend Duel: frozen words, one opponent, expiry, tie-break, anti-cheat, deep links, referral, XP."""

import json
import time
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from decks.models import Card, Deck
from duels import services
from duels.models import Duel, DuelParticipant
from gamification.models import UserAchievement
from telegram_auth.verify import sign_init_data
from words.models import Pack, UserLevelWord, UserWord, Word, WordTranslation

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-token"


@pytest.fixture
def words(db):
    pack = Pack.objects.create(track="en", level="A1", slug="p", name_uz="p", name_en="p", name_ru="p")
    out = []
    for i in range(20):
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
def opp(db):
    return User.objects.create_user(email="bek@example.com", password="secret123", display_name="Bek")


@pytest.fixture
def notices(monkeypatch, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    sent = []
    monkeypatch.setattr("telegram_bot.bot.send_to_user", lambda *a: sent.append(a))
    return sent


def make(api, **kw):
    r = api.post(
        "/api/duels/",
        {"track": "en", "source": "level", "source_ref": "A1", "mode": "speed", "translation_lang": "uz", **kw},
        format="json",
    )
    assert r.status_code == 201, r.data
    return r.data["code"]


def rewind(code, role, seconds=2.0):
    """Pretend the player thought for `seconds` (server clock)."""
    DuelParticipant.objects.filter(duel__code=code, role=role).update(
        last_answer_at=timezone.now() - timedelta(seconds=seconds)
    )


def run(client, code, role, right=10, seconds=2.0, headers=None):
    headers = headers or {}
    r = client.post(f"/api/duels/{code}/start/", **headers)
    assert r.status_code == 200, r.data
    duel = Duel.objects.get(code=code)
    for q in r.data["questions"]:
        a = duel.words[q["index"]]["answer"]
        rewind(code, role, seconds)
        choice = a if q["index"] < right else (a + 1) % len(q["options"])
        res = client.post(
            f"/api/duels/{code}/answer/", {"index": q["index"], "choice": choice}, format="json", **headers
        )
        assert res.status_code == 200, res.data
        assert res.data["correct"] is (q["index"] < right)
    res = client.post(f"/api/duels/{code}/finish/", **headers)
    assert res.status_code == 200, res.data
    return r.data, res.data


def test_both_players_get_the_same_frozen_questions_without_answers(api, client_for, opp, words):
    code = make(api)
    mine, _ = run(api, code, "creator")
    theirs, _ = run(client_for(opp), code, "opponent")
    assert mine["questions"] == theirs["questions"]
    assert len(mine["questions"]) == 10 and all(len(set(q["options"])) == 4 for q in mine["questions"])
    assert "answer" not in json.dumps(theirs["questions"])


def test_match_mode_uses_definitions_on_two_boards(api, words):
    code = make(api, mode="match")
    qs = api.post(f"/api/duels/{code}/start/").data["questions"]
    assert [q["board"] for q in qs] == [0] * 5 + [1] * 5
    assert qs[0]["options"] == qs[4]["options"] != qs[5]["options"]
    assert all(o.startswith("def ") for q in qs for o in q["options"])


def test_opponent_sees_challenge_but_no_answers(api, client_for, opp, words):
    code = make(api)
    # the creator has to play first
    assert client_for(opp).post(f"/api/duels/{code}/start/").status_code == 409
    run(api, code, "creator", right=8)
    d = APIClient().get(f"/api/duels/{code}/").data
    assert d["challenger"]["name"] == "Ali" and d["total"] == 10 and d["creator"]["score"] == 8
    assert "review" not in d and "questions" not in d


def test_one_opponent_per_code(api, client_for, opp, words):
    code = make(api)
    run(api, code, "creator")
    assert client_for(opp).post(f"/api/duels/{code}/start/").status_code == 200
    third = User.objects.create_user(email="c@example.com", password="secret123")
    assert client_for(third).post(f"/api/duels/{code}/start/").status_code == 409
    assert APIClient().post(f"/api/duels/{code}/start/").status_code == 409
    # resuming my own run is fine; an abandoned run frees the place
    assert client_for(opp).post(f"/api/duels/{code}/start/").status_code == 200
    rewind(code, "opponent", 3600)
    assert client_for(third).post(f"/api/duels/{code}/start/").status_code == 200


def test_expiry_after_48h_notifies_creator_once(api, user, client_for, opp, words, notices):
    user.telegram_id = 555
    user.save()
    code = make(api)
    run(api, code, "creator")
    duel = Duel.objects.get(code=code)
    assert timedelta(hours=47) < duel.expires_at - timezone.now() <= timedelta(hours=48)
    Duel.objects.filter(code=code).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert services.expire_due() == 1 and services.expire_due() == 0
    assert client_for(opp).post(f"/api/duels/{code}/start/").status_code == 410
    assert Duel.objects.get(code=code).status == "expired"
    assert len(notices) == 1 and notices[0][0] == 555


def test_tie_break_by_time_and_draw(api, client_for, opp, words):
    a, b = DuelParticipant(score=8, time_ms=1000), DuelParticipant(score=8, time_ms=1001)
    assert services.compare(a, b) == 1 and services.compare(b, a) == -1
    assert services.compare(a, DuelParticipant(score=9, time_ms=99999)) == -1
    assert services.compare(a, DuelParticipant(score=8, time_ms=1000)) == 0
    code = make(api)
    run(api, code, "creator", right=7, seconds=3)
    _, res = run(client_for(opp), code, "opponent", right=7, seconds=2)
    assert res["outcome"] == "win" and res["creator"]["score"] == res["opponent"]["score"] == 7


def test_anti_cheat(api, words):
    code = make(api)
    api.post(f"/api/duels/{code}/start/")
    url = f"/api/duels/{code}/answer/"
    r = api.post(url, {"index": 0, "choice": 0}, format="json")  # straight after the start
    assert r.status_code == 400 and r.data["detail"] == "too_fast"
    rewind(code, "creator")
    assert api.post(url, {"index": 0, "choice": 0, "client_ms": 120}, format="json").status_code == 400
    assert api.post(url, {"index": 0, "choice": 0, "client_ms": 1500}, format="json").status_code == 200
    rewind(code, "creator")
    assert api.post(url, {"index": 0, "choice": 1}, format="json").status_code == 409  # duplicate
    assert api.post(url, {"index": 99, "choice": 1}, format="json").status_code == 400
    assert api.post(url, {"index": 1, "choice": 9}, format="json").status_code == 400
    p = DuelParticipant.objects.get(duel__code=code)
    assert len(p.answers) == 1
    api.post(f"/api/duels/{code}/finish/")
    rewind(code, "creator")
    assert api.post(url, {"index": 1, "choice": 1}, format="json").status_code == 409


def test_xp_badges_learning_and_notification(api, user, client_for, opp, words, notices):
    user.telegram_id = 555
    user.save()
    code = make(api)
    run(api, code, "creator", right=6)
    assert UserLevelWord.objects.filter(user=user, found_at__isnull=False).count() == 6  # found = learned
    user.refresh_from_db()
    assert user.xp == 0 and user.streak == 1
    _, res = run(client_for(opp), code, "opponent", right=9)
    assert (res["outcome"], res["xp"]) == ("win", 30)
    user.refresh_from_db()
    opp.refresh_from_db()
    assert (user.xp, opp.xp) == (10, 30)
    assert UserAchievement.objects.filter(user=user, code="first_duel").exists()
    chat, text, _, path = notices[0]
    assert chat == 555 and "Bek" in text and "9/10" in text and path == f"/duel/{code}"
    # finishing again changes nothing
    client_for(opp).post(f"/api/duels/{code}/finish/")
    opp.refresh_from_db()
    assert opp.xp == 30 and len(notices) == 1
    s = api.get("/api/duels/").data
    assert (s["wins"], s["losses"]) == (0, 1)
    assert s["rivals"][0]["name"] == "Bek" and s["recent"][0]["outcome"] == "loss"


def test_missed_words_do_not_count_as_found(api, user, words):
    code = make(api)
    run(api, code, "creator", right=0)
    assert not UserLevelWord.objects.filter(user=user, found_at__isnull=False).exists()
    assert UserWord.objects.filter(user=user, box=1, miss_count=1).count() == 10


def test_draw_gives_15(api, user, client_for, opp, words):
    code = make(api)
    run(api, code, "creator")
    DuelParticipant.objects.filter(duel__code=code).update(time_ms=20000)
    c = client_for(opp)
    c.post(f"/api/duels/{code}/start/")
    DuelParticipant.objects.filter(duel__code=code, role="opponent").update(
        score=10, time_ms=20000, answers=[{"index": i, "choice": 0, "correct": True, "ms": 2000} for i in range(10)]
    )
    assert c.post(f"/api/duels/{code}/finish/").data["outcome"] == "draw"
    user.refresh_from_db()
    assert user.xp == 15


def test_guest_plays_then_claims_result(api, user, words):
    code = make(api)
    run(api, code, "creator", right=5)
    guest = APIClient()
    token = guest.post(f"/api/duels/{code}/start/").data["guest_token"]
    headers = {"HTTP_X_DUEL_GUEST": token}
    _, res = run(guest, code, "opponent", right=8, headers=headers)
    assert res["outcome"] == "win" and res["me"]["is_guest"] is True
    r = guest.post(
        "/api/auth/register/",
        {"email": "new@example.com", "password": "secret123", "display_name": "Nodir", "duel_code": code},
        format="json",
    )
    assert r.status_code == 201, r.data
    auth = {"HTTP_AUTHORIZATION": f"Bearer {r.data['access']}", **headers}
    for _ in range(2):  # the second claim is a no-op
        assert APIClient().post(f"/api/duels/{code}/claim/", **auth).status_code == 200
    nodir = User.objects.get(email="new@example.com")
    assert nodir.invited_by == user and nodir.xp == 30
    assert Duel.objects.get(code=code).winner == nodir
    # a stranger with the token of a claimed run gets nothing
    assert api.post(f"/api/duels/{code}/claim/", HTTP_X_DUEL_GUEST="wrong").data["me"]["role"] == "creator"


def test_rematch_swaps_roles_with_new_words(api, user, client_for, opp, words, notices):
    user.telegram_id = 555
    user.save()
    code = make(api)
    run(api, code, "creator")
    run(client_for(opp), code, "opponent")
    r = client_for(opp).post(f"/api/duels/{code}/rematch/")
    assert r.status_code == 201
    new = Duel.objects.get(code=r.data["code"])
    assert new.creator == opp and new.rematch_of.code == code and new.code != code
    assert client_for(opp).post(f"/api/duels/{code}/rematch/").data["code"] == new.code  # no duplicates
    run(client_for(opp), new.code, "creator")
    assert notices[-1][0] == 555 and "revansh" in notices[-1][1]
    run(api, new.code, "opponent")
    stranger = User.objects.create_user(email="s@example.com", password="secret123")
    assert client_for(stranger).post(f"/api/duels/{code}/rematch/").status_code == 400


def test_deck_duel_and_too_few_words(api, user, words):
    deck = Deck.objects.create(owner=user, name="Mine", track="en", translation_lang="ru")
    for i in range(9):
        Card.objects.create(deck=deck, term=f"t{i}", translation=f"tr{i}")
    body = {"track": "en", "source": "deck", "source_ref": str(deck.id), "mode": "speed"}
    r = api.post("/api/duels/", body, format="json")
    assert r.status_code == 400 and r.data["detail"] == "not_enough_words"
    Card.objects.create(deck=deck, term="t9", translation="tr9")
    r = api.post("/api/duels/", body, format="json")
    assert r.status_code == 201 and r.data["translation_lang"] == "ru"
    other = User.objects.create_user(email="o@example.com", password="secret123")
    d2 = Deck.objects.create(owner=other, name="Theirs", track="en")
    assert api.post("/api/duels/", {**body, "source_ref": str(d2.id)}, format="json").status_code == 404


def test_translation_language_rules(api, words):
    body = {"track": "en", "source": "level", "source_ref": "A1", "mode": "speed", "translation_lang": "en"}
    assert api.post("/api/duels/", body, format="json").status_code == 400
    code = make(api, translation_lang="de")
    assert all(o.startswith("de") for q in Duel.objects.get(code=code).words for o in q["options"])


# --- deep links and referral ----------------------------------------------------------------
def test_deep_links(api, words, settings):
    settings.TELEGRAM_BOT_USERNAME = "yodflip_bot"
    settings.PUBLIC_URL = "https://yodflip.onrender.com"
    settings.TELEGRAM_APP_SHORT_NAME = "play"
    code = make(api)
    d = api.get(f"/api/duels/{code}/").data
    assert d["telegram_link"] == f"https://t.me/yodflip_bot/play?startapp=duel_{code}"
    assert d["web_link"] == f"https://yodflip.onrender.com/duel/{code}"
    settings.TELEGRAM_APP_SHORT_NAME = ""
    assert api.get(f"/api/duels/{code}/").data["telegram_link"] == f"https://t.me/yodflip_bot?start=duel_{code}"
    assert services.code_from_param(f"duel_{code}") == code
    assert services.code_from_param("deck_x") == services.code_from_param("duel_../x") == ""


def tg_login(code, tg_id=42):
    pairs = {
        "user": json.dumps({"id": tg_id, "first_name": "Aziz"}),
        "auth_date": str(int(time.time())),
        "start_param": f"duel_{code}",
    }
    body = {"init_data": sign_init_data(pairs, TOKEN)}
    return APIClient().post("/api/auth/telegram/webapp/", body, format="json")


def test_telegram_startapp_registers_and_records_referral_once(api, user, client_for, opp, words, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    code = make(api)
    assert tg_login(code).status_code == 200
    aziz = User.objects.get(telegram_id=42)
    assert aziz.invited_by == user
    # a second link from somebody else doesn't change the referral
    other_code = make(client_for(opp))
    tg_login(other_code)
    aziz.refresh_from_db()
    assert aziz.invited_by == user
    assert api.get("/api/duels/").data["invited"] == 1
    # existing users are never counted as invited
    old = User.objects.create_user(telegram_id=43, display_name="Old")
    tg_login(code, 43)
    old.refresh_from_db()
    assert old.invited_by is None


def test_invited_5_badge(user, words, api):
    code = make(api)
    for i in range(5):
        u = User.objects.create_user(telegram_id=100 + i)
        services.record_referral(u, code)
    assert UserAchievement.objects.filter(user=user, code="invited_5").exists()
    assert services.record_referral(user, code) is False  # own link


def test_ten_wins_badge(api, user, client_for, opp, words):
    for _ in range(9):
        Duel.objects.create(
            creator=user, track="en", mode="speed", status="completed", winner=user, expires_at=timezone.now()
        )
    code = make(api)
    run(api, code, "creator")
    run(client_for(opp), code, "opponent", right=1)
    assert UserAchievement.objects.filter(user=user, code="duel_wins_10").exists()
