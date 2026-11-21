"""Translation language for memorization games: seed, API validation, decks, sets, OCR, prefs, stats."""

import importlib
import io
from unittest import mock

import pytest
from django.apps import apps
from django.core.management import call_command

from decks.models import Card, Deck, WordSet
from gamification.models import GameSession
from ocr.schema import validate_payload
from words.models import UserLevelWord, UserWord, Word, WordTranslation
from words.seedcheck import check_seed

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------- seed
def test_every_word_has_its_three_translations(seeded):
    assert Word.objects.count() == 2000
    for track, langs in (("en", {"uz", "ru", "de"}), ("de", {"uz", "ru", "en"})):
        words = Word.objects.filter(track=track).prefetch_related("translations")
        for w in words:
            got = {t.lang: t for t in w.translations.all()}
            assert set(got) == langs, w.display
            for t in got.values():
                assert t.text.strip() and t.example_translation.strip()
                assert t.text.strip().lower() != w.display.lower()
    assert not WordTranslation.objects.filter(word__track="en", lang="en").exists()
    assert not WordTranslation.objects.filter(word__track="de", lang="de").exists()


def test_seed_check_covers_translations():
    _, errors = check_seed()
    assert errors == []


def test_translation_seed_is_idempotent(seeded):
    before = dict(WordTranslation.objects.values_list("id", "text"))
    assert len(before) == 6000
    call_command("seed_words", "--force", stdout=io.StringIO())
    call_command("seed_words", stdout=io.StringIO())
    assert dict(WordTranslation.objects.values_list("id", "text")) == before


def test_migration_keeps_uzbek_data(seeded):
    mig = importlib.import_module("words.migrations.0003_wordtranslation")
    WordTranslation.objects.filter(lang="uz").delete()
    mig.copy_uzbek(apps, None)
    mig.copy_uzbek(apps, None)  # idempotent
    assert WordTranslation.objects.filter(lang="uz").count() == 2000
    w = Word.objects.get(track="en", word="apple")
    t = WordTranslation.objects.get(word=w, lang="uz")
    assert (t.text, t.example_translation) == (w.translation_uz, w.example_uz)


# -------------------------------------------------------------- validation
@pytest.mark.parametrize(
    "track,lang,direction",
    [("en", "en", "forward"), ("de", "de", "forward"), ("en", "xx", "forward"), ("en", "ru", "sideways")],
)
def test_invalid_pairs_are_rejected(api, seeded, track, lang, direction):
    q = {"game": "speed", "track": track, "source": "daily", "translation_lang": lang, "direction": direction}
    assert api.get("/api/games/words/", q).status_code == 400
    r = api.get(f"/api/levels/{track}/A1/round/", {"translation_lang": lang, "direction": direction})
    assert r.status_code == 400


def test_round_returns_the_chosen_language(api, seeded):
    r = api.get("/api/levels/en/A1/round/", {"size": 6, "translation_lang": "ru", "direction": "reverse"})
    assert r.status_code == 200
    assert r.data["translation_lang"] == "ru" and r.data["direction"] == "reverse"
    for item in r.data["words"]:
        t = WordTranslation.objects.get(word_id=item["word_id"], lang="ru")
        assert item["translation"] == t.text and item["translation_lang"] == "ru"
    de = api.get("/api/levels/de/A1/round/", {"size": 3, "translation_lang": "en"}).data
    assert all(i["translation_lang"] == "en" for i in de["words"])


def test_daily_challenge_same_words_in_each_users_language(api, client_for, seeded):
    from accounts.models import User

    other = client_for(User.objects.create_user(email="b@example.com", password="secret123"))
    uz = api.get("/api/games/words/", {"game": "daily", "track": "en", "source": "daily"}).data["items"]
    ru = other.get(
        "/api/games/words/", {"game": "daily", "track": "en", "source": "daily", "translation_lang": "ru"}
    ).data["items"]
    assert [i["word_id"] for i in uz] == [i["word_id"] for i in ru]
    assert uz[0]["translation"] != ru[0]["translation"]


# --------------------------------------------------------------- progress
def test_word_found_in_two_languages_counts_once(api, user, seeded):
    ru = api.get("/api/levels/en/A1/round/", {"size": 3, "translation_lang": "ru"}).data
    wid = ru["words"][0]["word_id"]
    api.post("/api/levels/answer/", {"session_id": ru["session_id"], "word_id": wid, "correct": True}, format="json")
    uz = api.get("/api/levels/en/A1/round/", {"size": 100, "translation_lang": "uz"}).data
    assert wid not in [w["word_id"] for w in uz["words"] if not w["is_filler"]]  # found: not offered again
    api.post("/api/levels/answer/", {"session_id": uz["session_id"], "word_id": wid, "correct": True}, format="json")
    assert UserLevelWord.objects.filter(user=user, found_at__isnull=False).count() == 1


def test_results_in_russian_do_not_overwrite_uzbek_lists(api, user, seeded):
    payload = {
        "game": "speed",
        "track": "en",
        "source": "missed",
        "translation_lang": "ru",
        "results": [{"term": "apple", "translation": "яблоко", "correct": True}],
    }
    assert api.post("/api/games/results/", payload, format="json").status_code == 200
    assert UserWord.objects.get(user=user, term_key="apple").translation_uz == ""
    assert GameSession.objects.get(user=user).translation_lang == "ru"
    bad = api.post("/api/games/results/", {**payload, "translation_lang": "en"}, format="json")
    assert bad.status_code == 400


def test_stats_breakdown_per_language(api, user, seeded):
    for lang, n in (("uz", 3), ("ru", 1)):
        for _ in range(n):
            GameSession.objects.create(user=user, track="en", game="speed", translation_lang=lang)
    GameSession.objects.create(user=user, track="en", game="match")  # definition game: no language
    data = api.get("/api/gamification/profile/", {"track": "en"}).data
    assert data["translation_langs"] == [
        {"lang": "uz", "count": 3, "percent": 75},
        {"lang": "ru", "count": 1, "percent": 25},
    ]


# ------------------------------------------------------------- preferences
def test_translation_preferences_per_track(api, seeded):
    r = api.get("/api/auth/translation-prefs/")
    assert r.data["en"] == {
        "track": "en",
        "preferred_translation_lang": "uz",
        "preferred_direction": "forward",
        "remember_choice": False,
    }
    body = {
        "track": "de",
        "preferred_translation_lang": "en",
        "preferred_direction": "reverse",
        "remember_choice": True,
    }
    assert api.put("/api/auth/translation-prefs/", body, format="json").data == body
    assert api.get("/api/auth/translation-prefs/").data["de"]["preferred_translation_lang"] == "en"
    assert api.get("/api/auth/translation-prefs/").data["en"]["preferred_translation_lang"] == "uz"
    bad = {**body, "preferred_translation_lang": "de"}
    assert api.put("/api/auth/translation-prefs/", bad, format="json").status_code == 400


# ---------------------------------------------------------------- decks
def test_deck_language_is_respected(api, user):
    r = api.post("/api/decks/", {"name": "RU", "track": "en", "translation_lang": "ru"}, format="json")
    assert r.status_code == 201, r.data
    deck = Deck.objects.get(pk=r.data["id"])
    Card.objects.create(deck=deck, term="apple", translation="яблоко")
    items = api.get(
        "/api/games/words/",
        {"game": "speed", "track": "en", "source": "deck", "id": deck.id, "translation_lang": "uz"},
    ).data
    assert items["translation_lang"] == "ru"  # the deck's language wins, no picker
    assert items["items"][0]["translation"] == "яблоко"
    bad = api.post("/api/decks/", {"name": "X", "track": "de", "translation_lang": "de"}, format="json")
    assert bad.status_code == 400


def test_deck_ai_translation_unavailable_and_cached(api, user, settings):
    deck = Deck.objects.create(owner=user, name="D", track="en", translation_lang="uz")
    card = Card.objects.create(deck=deck, term="apple", translation="olma")
    settings.ANTHROPIC_API_KEY = ""
    r = api.post(f"/api/decks/{deck.id}/translate/", {"lang": "ru"}, format="json")
    assert r.status_code == 503 and r.data["detail"] == "ai_unavailable"
    with mock.patch("decks.ai.translate_terms", return_value=["яблоко"]) as tr:
        r = api.post(f"/api/decks/{deck.id}/translate/", {"lang": "ru"}, format="json")
        assert r.status_code == 200
        api.post(f"/api/decks/{deck.id}/translate/", {"lang": "ru"}, format="json")
        assert tr.call_count == 1  # cached on the card
    card.refresh_from_db()
    assert card.extra_translations == {"ru": "яблоко"}
    assert api.post(f"/api/decks/{deck.id}/translate/", {"lang": "en"}, format="json").status_code == 400


# ------------------------------------------------------------ sets + OCR
def test_scanned_pairs_keep_translations_and_report_languages(api, user):
    body = {
        "name": "Page",
        "track": "en",
        "pairs": [
            {"word": "abundant", "definition": "a lot", "translation_uz": "mo'l", "translations": {"ru": "обильный"}},
            {"word": "rare", "definition": "not common", "translation_uz": "kamyob"},
        ],
    }
    r = api.post("/api/sets/", body, format="json")
    assert r.status_code == 201, r.data
    assert r.data["available_langs"] == ["uz", "ru"]
    ws = WordSet.objects.get(pk=r.data["id"])
    items = api.get(
        "/api/games/words/", {"game": "speed", "track": "en", "source": "set", "id": ws.id, "translation_lang": "ru"}
    ).data["items"]
    assert [(i["term"], i["translation"]) for i in items] == [("abundant", "обильный")]  # missing language: left out


def test_ocr_payload_carries_ru_and_other_language():
    data = validate_payload(
        {
            "language": "en",
            "pairs": [
                {
                    "word": "abundant",
                    "definition": "plentiful",
                    "part_of_speech": "adjective",
                    "article": None,
                    "translation_uz": "mo'l",
                    "translation_ru": "обильный",
                    "translation_alt": "reichlich",
                }
            ],
        }
    )
    assert data["pairs"][0]["translations"] == {"ru": "обильный", "de": "reichlich"}
    de = validate_payload(
        {
            "language": "de",
            "pairs": [
                {
                    "word": "Hund",
                    "definition": "ein Tier",
                    "part_of_speech": "noun",
                    "article": "der",
                    "translation_uz": "it",
                    "translation_ru": "",
                    "translation_alt": "dog",
                }
            ],
        }
    )
    assert de["pairs"][0]["translations"] == {"en": "dog"}
