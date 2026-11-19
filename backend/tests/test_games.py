from datetime import date

import pytest

from accounts.models import User
from decks.models import Card, Deck, WordSet
from games.sources import daily_words
from words.models import UserWord, Word

pytestmark = pytest.mark.django_db


def test_match_game_uses_same_language_definitions(api, seeded):
    r = api.get("/api/games/words/", {"game": "match", "track": "de", "source": "level", "level": "A1"})
    assert r.status_code == 200
    assert r.data["mode"] == "definition"
    assert len(r.data["items"]) == 60
    words = {w.display: w for w in Word.objects.filter(track="de", level="A1")}
    for item in r.data["items"]:
        assert item["definition"] == words[item["term"]].definition  # German definition, not Uzbek


def test_memorize_game_uses_uzbek(api, seeded):
    r = api.get("/api/games/words/", {"game": "speed", "track": "en", "source": "level", "level": "A1"})
    assert r.data["mode"] == "memorize"
    assert all(i["translation"] for i in r.data["items"])


def test_tracks_never_mix(api, seeded):
    r = api.get("/api/games/words/", {"game": "speed", "track": "en", "source": "level", "level": "A1"})
    en_terms = set(Word.objects.filter(track="en").values_list("word", flat=True))
    assert all(i["word"] in en_terms for i in r.data["items"])


def test_derdiedas_only_german(api, seeded):
    r = api.get("/api/games/words/", {"game": "derdiedas", "track": "en", "source": "level", "level": "A1"})
    assert r.status_code == 400
    r = api.get("/api/games/words/", {"game": "derdiedas", "track": "de", "source": "level", "level": "A1"})
    assert r.status_code == 200
    assert r.data["items"] and all(i["article"] in ("der", "die", "das") for i in r.data["items"])


def test_locked_level(api, seeded):
    r = api.get("/api/games/words/", {"game": "match", "track": "en", "source": "level", "level": "A2"})
    assert r.status_code == 403


def test_level_unlocks_at_70_percent(api, user, seeded):
    words = list(Word.objects.filter(track="en", level="A1"))
    for w in words[:42]:  # 70% of 60
        UserWord.objects.create(user=user, track="en", term_key=w.display.lower(), term=w.display, box=5, seen=True)
    levels = api.get("/api/words/levels/", {"track": "en"}).data["levels"]
    assert levels[0]["percent"] == 70
    assert levels[1]["unlocked"] is True
    assert levels[2]["unlocked"] is False


def test_results_update_leitner_xp_and_streak(api, user, seeded):
    payload = {
        "game": "match",
        "track": "en",
        "source": "level",
        "results": [
            {"term": "apple", "definition": "a fruit", "correct": False},
            {"term": "apple", "definition": "a fruit", "correct": True},
            {"term": "bread", "definition": "food", "correct": True},
        ],
        "duration_ms": 30000,
    }
    r = api.post("/api/games/results/", payload, format="json")
    assert r.status_code == 200, r.data
    assert r.data["xp_earned"] == 20
    assert r.data["accuracy"] == 67
    assert r.data["flips"] == 6
    assert "first_game" in r.data["new_achievements"]
    user.refresh_from_db()
    assert user.xp == 20 and user.streak == 1
    assert UserWord.objects.get(user=user, term_key="apple").box == 2
    assert UserWord.objects.get(user=user, term_key="bread").box == 2


def test_deck_and_set_sources(api, user):
    deck = Deck.objects.create(owner=user, name="D", track="de")
    Card.objects.create(deck=deck, term="der Hund", translation="it")
    Card.objects.create(deck=deck, term="Katze", translation="mushuk", article="die")
    r = api.get("/api/games/words/", {"game": "derdiedas", "track": "de", "source": "deck", "id": deck.id})
    assert {i["article"] for i in r.data["items"]} == {"der", "die"}
    # deck cards have no definition -> not usable in the definition game
    r = api.get("/api/games/words/", {"game": "match", "track": "de", "source": "deck", "id": deck.id})
    assert r.data["items"] == []
    ws = WordSet.objects.create(owner=user, name="S", track="en")
    ws.pairs.create(word="abundant", definition="a lot", translation_uz="mo'l")
    r = api.get("/api/games/words/", {"game": "match", "track": "en", "source": "set", "id": ws.id})
    assert r.data["items"][0]["definition"] == "a lot"
    r = api.get("/api/games/words/", {"game": "match", "track": "de", "source": "set", "id": ws.id})
    assert r.status_code == 400  # track mismatch


def test_other_users_private_deck_forbidden(user, client_for):
    other = User.objects.create_user(email="o@example.com", password="secret123")
    deck = Deck.objects.create(owner=other, name="P", track="en")
    r = client_for(user).get("/api/games/words/", {"game": "speed", "track": "en", "source": "deck", "id": deck.id})
    assert r.status_code == 403


def test_daily_challenge_is_same_for_everyone(seeded, user):
    d = date(2026, 3, 1)
    a = [w.id for w in daily_words("en", d)]
    assert len(a) == 10
    assert a == [w.id for w in daily_words("en", d)]
    assert a != [w.id for w in daily_words("en", date(2026, 3, 2))]


def test_daily_results_only_first_attempt_scores(api, seeded):
    items = api.get("/api/games/words/", {"game": "daily", "track": "en", "source": "daily"}).data["items"]
    results = [{"term": i["term"], "translation": i["translation"], "correct": True} for i in items]
    r1 = api.post(
        "/api/games/results/", {"game": "daily", "track": "en", "results": results, "duration_ms": 20000}, format="json"
    )
    assert r1.data["daily"]["first_attempt"] is True and r1.data["xp_earned"] > 0
    r2 = api.post(
        "/api/games/results/", {"game": "daily", "track": "en", "results": results, "duration_ms": 1000}, format="json"
    )
    assert r2.data["daily"]["first_attempt"] is False and r2.data["xp_earned"] == 0
    lb = api.get("/api/games/daily/leaderboard/", {"track": "en"}).data
    assert len(lb["entries"]) == 1 and lb["entries"][0]["is_me"]
