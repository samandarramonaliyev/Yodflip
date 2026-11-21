"""Two-sided flashcards ("Topdim" / "Topa olmadim", undo) and the paginated profile lists."""

import pytest

from decks.models import Card, Deck
from words.models import UserLevelWord, UserWord, Word

pytestmark = pytest.mark.django_db


def flash(api, cid, item, known, track="en", **extra):
    r = api.post(
        "/api/words/flash/answer/",
        {"client_id": cid, "track": track, "item": item, "known": known, **extra},
        format="json",
    )
    assert r.status_code == 200, r.data
    return r.data


def undo(api, answer_id):
    r = api.post("/api/words/flash/undo/", {"answer_id": answer_id}, format="json")
    assert r.status_code == 200, r.data
    return r.data


def lists(user, term):
    uw = UserWord.objects.filter(user=user, term_key=term.lower()).first()
    if uw is None:
        return None
    return {"learned": uw.is_learned, "want": uw.want_to_learn, "missed": uw.is_missed}


def test_topdim_goes_to_learned_and_leaves_other_lists(api, user):
    UserWord.objects.create(
        user=user, track="en", term_key="ocean", term="ocean", box=1, miss_count=2, want_to_learn=True
    )
    d = flash(api, "a1", {"term": "ocean", "translation": "okean"}, True)
    assert d["lists"] == {"learned": True, "want": False, "missed": False}
    assert lists(user, "ocean") == {"learned": True, "want": False, "missed": False}


def test_topa_olmadim_goes_to_want_and_leaves_learned(api, user):
    UserWord.objects.create(user=user, track="en", term_key="river", term="river", box=5, seen=True)
    d = flash(api, "b1", {"term": "river", "translation": "daryo"}, False)
    assert d["lists"]["want"] is True and d["lists"]["learned"] is False
    assert lists(user, "river")["want"] is True


def test_undo_restores_the_previous_state_exactly(api, user):
    uw = UserWord.objects.create(
        user=user, track="en", term_key="river", term="river", box=3, correct_count=4, miss_count=1, seen=True
    )
    before = (
        UserWord.objects.filter(pk=uw.pk).values("box", "correct_count", "miss_count", "want_to_learn", "due_at").get()
    )
    a = flash(api, "c1", {"term": "river"}, True)
    undo(api, a["answer_id"])
    assert (
        UserWord.objects.filter(pk=uw.pk).values("box", "correct_count", "miss_count", "want_to_learn", "due_at").get()
        == before
    )
    # an answer that created the row: undo removes it again
    b = flash(api, "c2", {"term": "brand-new", "translation": "yangi"}, False)
    assert lists(user, "brand-new")["want"] is True
    undo(api, b["answer_id"])
    assert lists(user, "brand-new") is None
    assert undo(api, b["answer_id"])["undone"] is True  # repeated undo is harmless


def test_duplicate_requests_are_idempotent(api, user):
    a = flash(api, "same", {"term": "apple"}, True)
    b = flash(api, "same", {"term": "apple"}, True)
    assert b["duplicate"] is True and b["answer_id"] == a["answer_id"]
    assert UserWord.objects.get(user=user, term_key="apple").correct_count == 1


def test_level_word_topdim_counts_once_and_miss_never_reduces(api, user, seeded):
    w = Word.objects.get(track="en", word="apple")
    item = {"term": w.display, "word_id": w.id, "translation": "яблоко", "translation_lang": "ru"}
    first = flash(api, "l1", item, True)
    assert first["level_found_now"] is True and first["level_progress"]["found"] == 1
    undo(api, first["answer_id"])  # undoing the answer that found it removes the mark again
    assert UserLevelWord.objects.filter(user=user, found_at__isnull=False).count() == 0
    assert flash(api, "l2", item, True)["level_found_now"] is True
    assert flash(api, "l3", item, True)["level_found_now"] is False  # repeated Topdim: no double count
    flash(api, "l4", item, False)  # "Topa olmadim" later: still found
    assert UserLevelWord.objects.filter(user=user, found_at__isnull=False).count() == 1
    assert UserWord.objects.get(user=user, word=w).translation_uz == w.translation_uz  # never Russian text


def test_deck_cards_update_deck_stats(api, user):
    deck = Deck.objects.create(owner=user, name="My", track="de", translation_lang="ru")
    c1 = Card.objects.create(deck=deck, term="der Hund", translation="собака")
    c2 = Card.objects.create(deck=deck, term="die Katze", translation="кошка")
    a = flash(
        api, "d1", {"term": "der Hund", "translation": "собака", "translation_lang": "ru"}, True, "de", card_id=c1.id
    )
    flash(
        api, "d2", {"term": "die Katze", "translation": "кошка", "translation_lang": "ru"}, False, "de", card_id=c2.id
    )
    data = api.get(f"/api/decks/{deck.id}/").data
    assert (data["known_count"], data["learning_count"]) == (1, 1)
    assert lists(user, "der hund")["learned"] is True  # custom words behave the same way
    assert UserWord.objects.get(user=user, term_key="der hund").translation_uz == ""  # Russian not stored as Uzbek
    undo(api, a["answer_id"])
    c1.refresh_from_db()
    assert c1.study_status == ""


def test_results_for_flashcards_do_not_touch_lists(api, user):
    flash(api, "r1", {"term": "cloud"}, False)
    payload = {"game": "flashcards", "track": "en", "source": "want", "results": [{"term": "cloud", "correct": False}]}
    assert api.post("/api/games/results/", payload, format="json").status_code == 200
    assert lists(user, "cloud") == {"learned": False, "want": True, "missed": False}  # not moved to Missed


# ------------------------------------------------------------------ profile lists
def test_my_words_paginated_with_counts_search_sort_level(api, user, seeded):
    words = list(Word.objects.filter(track="en", level="A1").order_by("id")[:40])
    for w in words:
        UserWord.objects.create(user=user, track="en", term_key=w.display.lower(), term=w.display, box=5, word=w)
    UserWord.objects.create(user=user, track="en", term_key="zebra", term="zebra", want_to_learn=True)
    r = api.get("/api/me/words/", {"list": "learned", "track": "en", "page_size": 6})
    assert r.data["count"] == 40 and len(r.data["results"]) == 6 and r.data["has_more"]
    assert r.data["counts"] == {"learned": 40, "want": 1, "missed": 0}
    p1 = api.get("/api/me/words/", {"list": "learned", "track": "en"}).data
    p2 = api.get("/api/me/words/", {"list": "learned", "track": "en", "page": 2}).data
    assert len(p1["results"]) == 30 and len(p2["results"]) == 10 and not p2["has_more"]
    assert not {x["id"] for x in p1["results"]} & {x["id"] for x in p2["results"]}
    s = api.get("/api/me/words/", {"list": "learned", "track": "en", "search": "apple"}).data
    assert [x["term"] for x in s["results"]] == ["apple"]
    az = api.get("/api/me/words/", {"list": "learned", "track": "en", "sort": "az"}).data["results"]
    assert [x["term"] for x in az] == sorted(x["term"] for x in az)
    assert api.get("/api/me/words/", {"list": "learned", "track": "en", "level": "B2"}).data["count"] == 0
    assert az[0]["level"] == "A1"
    assert api.get("/api/me/words/", {"list": "nope"}).status_code == 400


def test_my_words_filter_by_deck(api, user):
    deck = Deck.objects.create(owner=user, name="D", track="en")
    Card.objects.create(deck=deck, term="apple", translation="olma")
    for t in ("apple", "pear"):
        UserWord.objects.create(user=user, track="en", term_key=t, term=t, want_to_learn=True)
    r = api.get("/api/me/words/", {"list": "want", "track": "en", "deck": deck.id}).data
    assert [x["term"] for x in r["results"]] == ["apple"]
