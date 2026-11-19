import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from accounts.models import User
from decks.models import Card, Deck

pytestmark = pytest.mark.django_db


def test_deck_crud_and_cards(api):
    r = api.post("/api/decks/", {"name": "Fruits", "track": "en"}, format="json")
    assert r.status_code == 201
    did = r.data["id"]
    r = api.post(f"/api/decks/{did}/cards/", {"term": "apple", "translation": "olma"}, format="json")
    assert r.status_code == 201
    cid = r.data["id"]
    r = api.patch(f"/api/decks/{did}/cards/{cid}/", {"translation": "olma (meva)"}, format="json")
    assert r.data["translation"] == "olma (meva)"
    detail = api.get(f"/api/decks/{did}/").data
    assert detail["card_count"] == 1 and detail["cards"][0]["term"] == "apple"
    assert api.delete(f"/api/decks/{did}/cards/{cid}/").status_code == 204


def test_first_deck_achievement(api, user):
    api.post("/api/decks/", {"name": "X", "track": "en"}, format="json")
    assert user.achievements.filter(code="first_deck").exists()


def test_reorder(api, user):
    deck = Deck.objects.create(owner=user, name="D", track="en")
    a = Card.objects.create(deck=deck, term="a", translation="1", order=0)
    b = Card.objects.create(deck=deck, term="b", translation="2", order=1)
    api.post(f"/api/decks/{deck.id}/reorder/", {"ids": [b.id, a.id]}, format="json")
    assert [c.term for c in deck.cards.all()] == ["b", "a"]


def test_share_and_copy(user, client_for):
    deck = Deck.objects.create(owner=user, name="Shared", track="de", is_public=True)
    Card.objects.create(deck=deck, term="der Hund", translation="it", article="der")
    anon = APIClient().get(f"/api/decks/shared/{deck.share_code}/")
    assert anon.status_code == 200 and anon.data["cards"][0]["term"] == "der Hund"
    other = User.objects.create_user(email="b@example.com", password="secret123")
    r = client_for(other).post(f"/api/decks/shared/{deck.share_code}/")
    assert r.status_code == 201
    copy = Deck.objects.get(pk=r.data["id"])
    assert copy.owner == other and copy.cards.count() == 1 and copy.copied_from == deck


def test_private_deck_not_shared(user):
    deck = Deck.objects.create(owner=user, name="Private", track="en")
    assert APIClient().get(f"/api/decks/shared/{deck.share_code}/").status_code == 404


def test_cannot_touch_others_deck(user, client_for):
    other = User.objects.create_user(email="c@example.com", password="secret123")
    deck = Deck.objects.create(owner=other, name="Theirs", track="en")
    assert client_for(user).get(f"/api/decks/{deck.id}/").status_code == 404


def test_csv_import_export(api, user):
    deck = Deck.objects.create(owner=user, name="CSV", track="en")
    f = SimpleUploadedFile("d.csv", b"term,translation,definition\napple,olma,a fruit\nbread,non,\n", "text/csv")
    r = api.post(f"/api/decks/{deck.id}/import/", {"file": f}, format="multipart")
    assert r.status_code == 201 and r.data["added"] == 2
    out = api.get(f"/api/decks/{deck.id}/export/")
    assert out.status_code == 200
    assert b"apple,olma,a fruit" in out.content


def test_quick_add_and_set_to_deck(api, user):
    deck = Deck.objects.create(owner=user, name="Q", track="en")
    r = api.post("/api/decks/quick-add/", {"deck_id": deck.id, "term": "cat", "translation": "mushuk"}, format="json")
    assert r.status_code == 201
    r = api.post("/api/decks/quick-add/", {"deck_id": deck.id, "term": "Cat"}, format="json")
    assert r.data["detail"] == "duplicate"
    s = api.post(
        "/api/sets/",
        {
            "name": "Page 12",
            "track": "en",
            "pairs": [{"word": "abundant", "definition": "a lot", "translation_uz": "mo'l"}],
        },
        format="json",
    )
    assert s.status_code == 201
    d = api.post(f"/api/sets/{s.data['id']}/to-deck/")
    assert d.status_code == 201 and d.data["card_count"] == 1


def test_word_lists_flow(api):
    r = api.post(
        "/api/words/lists/want/add/",
        {"track": "en", "term": "serendipity", "translation_uz": "tasodifiy omad"},
        format="json",
    )
    assert r.status_code == 201
    uid = r.data["id"]
    lst = api.get("/api/words/lists/want/", {"track": "en"}).data
    assert len(lst) == 1
    assert api.get("/api/words/lists/want/", {"track": "de"}).data == []
    api.patch(f"/api/words/mine/{uid}/", {"to": "learned"}, format="json")
    assert len(api.get("/api/words/lists/learned/", {"track": "en"}).data) == 1
    assert api.get("/api/words/lists/want/", {"track": "en", "q": "seren"}).data == []
    api.delete(f"/api/words/mine/{uid}/")
    assert api.get("/api/words/lists/learned/", {"track": "en"}).data == []


def test_profile_and_leaderboard(api, user):
    p = api.get("/api/gamification/profile/", {"track": "en"}).data
    assert len(p["chart"]) == 7 and p["level"] == 1
    lb = api.get("/api/gamification/leaderboard/", {"period": "weekly"}).data
    assert lb["period"] == "weekly"
    ach = api.get("/api/gamification/achievements/").data
    assert any(a["code"] == "streak_7" for a in ach)
