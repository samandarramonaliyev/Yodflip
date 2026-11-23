"""Exam prep packs: seed counts / idempotency, shared words, rounds, goal, badges, simulation."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from duels.models import Duel
from exams import services
from exams.models import ExamPack, ExamSimulation, ExamTopic, PackWord
from exams.seedfiles import PACKS, check
from gamification.models import GameSession, UserAchievement
from words.levels import LEVEL_SIZES
from words.models import Pack, UserLevelWord, UserWord, Word, WordTranslation, term_key

pytestmark = pytest.mark.django_db


# --- seed -----------------------------------------------------------------------------------
def test_seed_files_pass_the_check():
    counts, errors = check()
    assert errors == []
    assert counts == {
        "goethe-a1": 300,
        "goethe-a2": 400,
        "goethe-b1": 500,
        "ielts-academic": 500,
        "core-1000": 1000,
    }


def test_seed_counts_idempotency_and_no_duplicate_words(seeded):
    call_command("seed_exams", verbosity=0, stdout=StringIO())
    snapshot = set(PackWord.objects.values_list("id", "word_id"))
    words, translations = Word.objects.count(), WordTranslation.objects.count()
    for p in PACKS:
        pack = ExamPack.objects.get(slug=p.slug)
        assert pack.pack_words.count() == p.count
        assert set(pack.pack_words.values_list("word__track", flat=True)) == {p.track}
    # no duplicate Word rows inside a track
    keys = [(w.track, term_key(w.display)) for w in Word.objects.all()]
    assert len(keys) == len(set(keys))
    # level sizes are untouched
    for track in ("en", "de"):
        for level, n in LEVEL_SIZES.items():
            assert Word.objects.filter(track=track, level=level).count() == n
    # every pack word has all fields and three translations
    qs = Word.objects.filter(exam_links__isnull=False).distinct()
    assert not qs.filter(definition="").exists() and not qs.filter(example="").exists()
    assert not qs.filter(part_of_speech="").exists()
    for lang, track in (("uz", "en"), ("ru", "en"), ("de", "en"), ("uz", "de"), ("ru", "de"), ("en", "de")):
        missing = qs.filter(track=track).exclude(translations__lang=lang)
        assert not missing.exists(), (lang, list(missing[:3]))
    assert not WordTranslation.objects.filter(word__in=qs, example_translation="").exists()
    assert not Word.objects.filter(exam_links__pack__slug="ielts-academic", collocations="").exists()
    assert not Word.objects.filter(track="de", part_of_speech="noun", article="").exists()
    # second run (forced): the same rows, the same ids
    call_command("seed_exams", "--force", verbosity=0, stdout=StringIO())
    assert snapshot == set(PackWord.objects.values_list("id", "word_id"))
    assert (words, translations) == (Word.objects.count(), WordTranslation.objects.count())
    out = StringIO()
    call_command("seed_exams", stdout=out)
    assert "Skipping" in out.getvalue()
    call_command("seed_words", "--force", verbosity=0, stdout=StringIO())  # the level seed leaves them alone
    assert PackWord.objects.count() == 2700 and Word.objects.count() == words


# --- small fixtures ---------------------------------------------------------------------------
@pytest.fixture
def pack(db):
    """40 words in 4 topics; the first 10 are also the whole A1 level."""
    theme = Pack.objects.create(track="en", level="A1", slug="p", name_uz="p", name_en="p", name_ru="p")
    exam = ExamPack.objects.create(track="en", slug="mini", name_uz="Mini", name_en="Mini", name_ru="Mini")
    topics = [
        ExamTopic.objects.create(pack=exam, slug=f"t{i}", name_uz=f"T{i}", name_en="T", name_ru="T", order=i)
        for i in range(4)
    ]
    for i in range(40):
        shared = i < 10
        w = Word.objects.create(
            track="en",
            level="A1" if shared else "",
            pack=theme if shared else None,
            word=f"w{i}",
            part_of_speech="noun",
            definition=f"def {i}",
            translation_uz=f"uz{i}",
            example=f"ex {i}",
            example_uz=f"mi {i}",
        )
        for lang in ("uz", "ru", "de"):
            WordTranslation.objects.create(word=w, lang=lang, text=f"{lang}{i}", example_translation="x")
        PackWord.objects.create(pack=exam, word=w, topic=topics[i // 10], order=i)
    return exam


def get_round(api, **params):
    r = api.get("/api/exams/mini/round/", {"size": 10, "game": "speed", **params})
    assert r.status_code == 200, r.data
    return r.data


def answer(api, sid, ids, correct=True):
    body = {"session_id": sid, "answers": [{"word_id": i, "correct": correct} for i in ids]}
    r = api.post("/api/levels/answer/", body, format="json")
    assert r.status_code == 200, r.data
    return r.data


def find_all(api, **params):
    for _ in range(20):
        d = get_round(api, **params)
        if d["completed"] or d["pool_done"]:
            return d
        answer(api, d["session_id"], [w["word_id"] for w in d["words"]])
    raise AssertionError("not finished")


# --- progress -------------------------------------------------------------------------------
def test_shared_word_counts_once_for_level_and_pack(api, user, pack):
    d = get_round(api, topic="t0")  # the 10 words that are also level A1
    out = answer(api, d["session_id"], [w["word_id"] for w in d["words"]])
    assert (out["progress"]["found"], out["progress"]["total"]) == (10, 40)
    levels = api.get("/api/levels/en/").data["levels"]
    assert (levels[0]["found"], levels[0]["total"], levels[0]["completed"]) == (10, 10, True)
    answer(api, d["session_id"], [w["word_id"] for w in d["words"]])  # retry: nothing is counted twice
    assert UserLevelWord.objects.filter(user=user, found_at__isnull=False).count() == 10
    assert api.get("/api/exams/mini/").data["found"] == 10
    user.refresh_from_db()
    assert user.xp == 200  # level completion bonus, once
    assert UserWord.objects.filter(user=user, box=5).count() == 10


def test_level_game_counts_for_the_pack_too(api, pack):
    d = api.get("/api/levels/en/A1/round/", {"size": 10, "game": "speed"}).data
    answer(api, d["session_id"], [w["word_id"] for w in d["words"]])
    row = api.get("/api/exams/", {"track": "en"}).data["packs"][0]
    assert (row["found"], row["total"], row["percent"], row["topic_count"]) == (10, 40, 25, 4)


def test_exam_only_words_never_change_levels(api, pack):
    d = get_round(api, topic="t2")
    answer(api, d["session_id"], [w["word_id"] for w in d["words"]])
    levels = api.get("/api/levels/en/").data["levels"]
    assert levels[0]["total"] == 10 and all(lv["found"] == 0 for lv in levels)
    assert len(api.get("/api/words/levels/A1/", {"track": "en"}).data) == 10


def test_results_screen_and_xp_once(api, pack):
    d = get_round(api, topic="t1")
    body = {
        "game": "speed",
        "track": "en",
        "source": "exam",
        "session_id": d["session_id"],
        "results": [{"term": w["term"], "word_id": w["word_id"], "correct": True} for w in d["words"]],
    }
    r = api.post("/api/games/results/", body, format="json")
    assert r.status_code == 200 and r.data["xp_earned"] == 48  # 10 × 4 + 20%
    assert r.data["level_round"]["progress"]["exam"] == "mini" and r.data["level_round"]["new_found_count"] == 10
    assert api.post("/api/games/results/", body, format="json").data["xp_earned"] == 0
    assert api.post("/api/games/results/", {**body, "session_id": ""}, format="json").status_code == 400


def test_topics_continue_and_pool_done(api, pack):
    assert api.get("/api/exams/mini/").data["next_topic"] == "t0"
    d = get_round(api, topic="t2", size=5)
    answer(api, d["session_id"], [w["word_id"] for w in d["words"]])
    data = api.get("/api/exams/mini/").data
    assert data["next_topic"] == "t2"  # continues where the user stopped
    assert [t["found"] for t in data["topics"]] == [0, 0, 5, 0]
    assert find_all(api, topic="t2")["pool_done"] is True
    assert api.get("/api/exams/mini/").data["next_topic"] == "t0"
    assert find_all(api)["completed"] is True


def test_badges_at_50_and_100_percent(api, user, pack):
    def badges():
        return set(UserAchievement.objects.filter(user=user, code__startswith="exam").values_list("code", flat=True))

    find_all(api, topic="t0")
    assert badges() == set()
    find_all(api, topic="t1")
    assert badges() == {"exam_pack_50"}
    find_all(api)
    assert badges() == {"exam_pack_50", "exam_pack_100"}


def test_flashcards_count_for_the_pack(api, pack):
    w = Word.objects.get(word="w20")
    body = {"client_id": "c1", "track": "en", "item": {"term": "w20", "word_id": w.id}, "known": True}
    r = api.post("/api/words/flash/answer/", body, format="json")
    assert r.status_code == 200 and r.data["level_found_now"] is True
    assert api.get("/api/exams/mini/").data["found"] == 1


def test_words_and_review_source(api, pack):
    r = api.get("/api/exams/mini/words/", {"topic": "t1", "translation_lang": "ru"})
    assert [w["word"] for w in r.data] == [f"w{i}" for i in range(10, 20)] and r.data[0]["translation"] == "ru10"
    q = {"game": "speed", "track": "en", "source": "examreview", "pack": "mini", "topic": "t1,t2"}
    items = api.get("/api/games/words/", q).data["items"]
    assert len(items) == 20
    body = {
        "game": "speed",
        "track": "en",
        "source": "examreview",
        "results": [{"term": i["term"], "word_id": i["word_id"], "correct": True} for i in items[:3]],
    }
    assert api.post("/api/games/results/", body, format="json").status_code == 200
    assert api.get("/api/exams/mini/").data["found"] == 3


def test_duel_from_pack(api, pack):
    body = {"track": "en", "source": "exam", "source_ref": "mini", "mode": "match"}
    r = api.post("/api/duels/", body, format="json")
    assert r.status_code == 201 and len(Duel.objects.get(code=r.data["code"]).words) == 10
    assert api.post("/api/duels/", {**body, "track": "de"}, format="json").status_code == 400


def test_daily_goal(api, user, pack):
    assert api.get("/api/exams/goal/").data["goal"] is None
    g = api.post("/api/exams/mini/goal/", {"per_day": 5}, format="json").data["goal"]
    assert (g["per_day"], g["done"], g["reached"]) == (5, 0, False)
    d = get_round(api)
    answer(api, d["session_id"], [w["word_id"] for w in d["words"]][:5])
    g = api.get("/api/exams/goal/").data["goal"]
    assert (g["done"], g["reached"]) == (5, True)
    UserLevelWord.objects.filter(user=user).update(found_at=timezone.now() - timedelta(days=2))
    assert api.get("/api/exams/mini/").data["goal"]["done"] == 0
    assert api.post("/api/exams/mini/goal/", {"per_day": 0}, format="json").data["goal"] is None


# --- simulation -----------------------------------------------------------------------------
def test_scoring_and_weak_topics():
    qs = [{"topic": t, "answer": 0} for t in ["a"] * 4 + ["b"] * 2 + ["c"] * 4]
    # a: 4/4, b: 1/2, c: 2/4 (one unanswered)
    res = services.score_simulation(qs, {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 0, 7: 0, 8: 3})
    assert (res["score"], res["total"], res["percent"]) == (7, 10, 70)
    assert {t["slug"]: t["percent"] for t in res["topics"]} == {"a": 100, "b": 50, "c": 50}
    assert set(res["weak_topics"]) == {"b", "c"}


def start(api):
    r = api.post("/api/exams/mini/simulation/", {"translation_lang": "uz"}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def test_simulation_flow(api, user, pack):
    d = start(api)
    assert len(d["questions"]) == 30 and d["time_limit"] == 600
    assert {q["kind"] for q in d["questions"]} == {"translation", "reverse", "definition"}
    assert "answer" not in str(d["questions"])
    sim = ExamSimulation.objects.get()
    assert {q["topic"] for q in sim.questions} == {"t0", "t1", "t2", "t3"}
    assert len({q["word_id"] for q in sim.questions}) == 30
    # everything right except topic t3
    answers = [
        {"index": n, "choice": q["answer"] if q["topic"] != "t3" else (q["answer"] + 1) % 4}
        for n, q in enumerate(sim.questions)
    ]
    wrong = sum(q["topic"] == "t3" for q in sim.questions)
    url = f"/api/exams/simulations/{sim.pk}/submit/"
    r = api.post(url, {"answers": answers}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["score"] == 30 - wrong and r.data["weak_topics"] == ["t3"]
    assert r.data["topics"][0]["name"]["uz"] == "T3" and r.data["xp"] == 5 * (30 - wrong)
    assert UserLevelWord.objects.filter(user=user, found_at__isnull=False).count() == 30 - wrong
    assert UserWord.objects.filter(user=user, box=1, miss_count=1).count() == wrong
    user.refresh_from_db()
    xp = user.xp
    again = api.post(url, {"answers": []}, format="json")  # scored only once
    assert again.data["score"] == 30 - wrong
    user.refresh_from_db()
    assert user.xp == xp and user.streak == 1 and GameSession.objects.filter(game="exam_sim").count() == 1
    assert api.get("/api/exams/mini/").data["last_simulation"]["score"] == 30 - wrong


def test_late_simulation_gives_no_xp_and_is_private(api, client_for, pack, django_user_model):
    d = start(api)
    other = django_user_model.objects.create_user(email="x@example.com", password="secret123")
    url = f"/api/exams/simulations/{d['id']}/submit/"
    assert client_for(other).post(url, {"answers": []}, format="json").status_code == 404
    ExamSimulation.objects.update(created_at=timezone.now() - timedelta(hours=1))
    q = ExamSimulation.objects.get().questions[0]
    r = api.post(url, {"answers": [{"index": 0, "choice": q["answer"]}]}, format="json")
    assert r.data["late"] is True and r.data["xp"] == 0 and r.data["score"] == 1


def test_unknown_pack_and_german_only_game(api, pack):
    assert api.get("/api/exams/nope/").status_code == 404
    assert api.get("/api/exams/mini/round/", {"game": "derdiedas"}).status_code == 400
