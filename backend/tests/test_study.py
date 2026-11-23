"""Word list study mode: lessons of 20, language, filters, no progress changes."""

import pytest
from django.utils import timezone

from words.models import Pack, UserLevelWord, UserWord, Word, WordTranslation

pytestmark = pytest.mark.django_db
URL = "/api/levels/en/A1/words/"


@pytest.fixture
def level(db):
    packs = [
        Pack.objects.create(track="en", level="A1", slug=s, name_uz=s, name_en=s, name_ru=s, order=n)
        for n, s in enumerate(("food", "travel"))
    ]
    for i in range(45):
        w = Word.objects.create(
            track="en", level="A1", pack=packs[i >= 30], word=f"word{i:02}", part_of_speech="noun",
            definition="d", translation_uz=f"soz{i}", example=f"Example {i}.", example_uz=f"Misol {i}.",
        )  # fmt: skip
        for lang in ("uz", "ru", "de"):
            WordTranslation.objects.create(word=w, lang=lang, text=f"{lang}{i}", example_translation=f"ex-{lang}{i}")
    Word.objects.create(track="en", level="A2", pack=packs[0], word="other", part_of_speech="n", definition="d")
    return packs


def get(api, **p):
    r = api.get(URL, p)
    assert r.status_code == 200, r.data
    return r.data


def test_lessons_of_20(api, level):
    d = get(api)
    assert (d["lesson"], d["lessons"], d["total"], d["lesson_size"]) == (1, 3, 45, 20)
    words = [w["word"] for n in (1, 2, 3) for w in get(api, lesson=n)["words"]]
    assert words == [f"word{i:02}" for i in range(45)]
    assert len(get(api, lesson=3)["words"]) == 5 and get(api, lesson=99)["lesson"] == 3
    assert api.get(URL, {"lesson": "x"}).status_code == 400


@pytest.mark.parametrize("lang", ["uz", "ru", "de"])
def test_translation_language(api, level, lang):
    w = get(api, lang=lang)["words"][0]
    assert w["translation"] == f"{lang}0" and w["example_tr"] == f"ex-{lang}0" and w["example"] == "Example 0."
    assert api.get(URL, {"lang": "en"}).status_code == 400


def test_search_topic_and_unlearned(api, user, level):
    assert [w["word"] for w in get(api, search="WORD07")["words"]] == ["word07"]
    assert [w["word"] for w in get(api, search="ru44", lang="ru")["words"]] == ["word44"]
    assert get(api, topic="travel")["total"] == 15
    assert [t["slug"] for t in get(api)["topics"]] == ["food", "travel"]
    w = Word.objects.get(word="word00")
    UserLevelWord.objects.create(user=user, word=w, track="en", level="A1", found_at=timezone.now())
    UserWord.objects.create(user=user, track="en", term_key="word01", term="word01", box=5)
    d = get(api)
    assert [x["learned"] for x in d["words"][:3]] == [True, True, False]
    d = get(api, only_unlearned="true")
    assert d["total"] == 43 and d["words"][0]["word"] == "word02"


def test_star_and_reading_changes_nothing(api, user, level):
    for n in (1, 2, 3):
        get(api, lesson=n, lang="ru")
    assert not UserWord.objects.exists() and not UserLevelWord.objects.exists()
    user.refresh_from_db()
    assert (user.xp, user.last_active_date) == (0, None)
    w = get(api)["words"][0]
    body = {"track": "en", "term": w["term"], "word_id": w["id"], "translation_uz": w["translation_uz"]}
    assert api.post("/api/words/lists/want/add/", body, format="json").status_code == 201
    w = get(api)["words"][0]
    assert w["want"] is True and w["learned"] is False
    api.delete(f"/api/words/mine/{w['userword_id']}/?list=want")
    assert get(api)["words"][0]["want"] is False
    assert api.get("/api/levels/en/").data["levels"][0]["found"] == 0


def test_locked_level(api, level):
    assert api.get("/api/levels/en/A2/words/").status_code == 403


def test_flashcards_with_exactly_this_lesson(api, level):
    ids = [w["id"] for w in get(api, lesson=2)["words"]]
    q = {"game": "flashcards", "track": "en", "source": "lesson", "level": "A1", "ids": ",".join(map(str, ids))}
    items = api.get("/api/games/words/", q).data["items"]
    assert {i["word_id"] for i in items} == set(ids) and len(items) == 20
    other = Word.objects.get(word="other").id
    assert api.get("/api/games/words/", {**q, "ids": str(other)}).data["items"] == []
    assert api.get("/api/games/words/", {**q, "level": "A2"}).status_code == 403
