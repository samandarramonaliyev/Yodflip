"""Level progress rules: FOUND = LEARNED, fillers, unlocking, completion, seed, migration."""

import importlib
import io

import pytest
from django.apps import apps
from django.core.management import call_command
from django.utils import timezone

from accounts.models import User
from gamification.models import UserAchievement
from words.levels import COMPLETION_BONUS_XP, LEVEL_SIZES, backfill_from_leitner, unlock_target
from words.models import LevelCompletion, UserLevelWord, UserWord, Word
from words.seedcheck import check_seed

pytestmark = pytest.mark.django_db


def get_round(api, track="en", level="A1", size=6, **extra):
    r = api.get(f"/api/levels/{track}/{level}/round/", {"size": size, **extra})
    assert r.status_code == 200, r.data
    return r.data


def answer(api, session_id, word_id, correct=True):
    r = api.post(
        "/api/levels/answer/", {"session_id": session_id, "word_id": word_id, "correct": correct}, format="json"
    )
    assert r.status_code == 200, r.data
    return r.data


def found_count(user, track="en", level="A1"):
    return UserLevelWord.objects.filter(user=user, track=track, level=level, found_at__isnull=False).count()


def mark_found(user, words):
    now = timezone.now()
    for w in words:
        UserLevelWord.objects.update_or_create(
            user=user, word=w, defaults={"track": w.track, "level": w.level, "found_at": now}
        )


# ------------------------------------------------------------------ found = learned
def test_found_word_is_counted_once(api, user, seeded):
    rnd = get_round(api)
    wid = rnd["words"][0]["word_id"]
    first = answer(api, rnd["session_id"], wid)
    assert first["new_found"] == [wid]
    assert first["progress"]["found"] == 1
    # repeated correct answers and duplicate requests (network retries, double taps)
    for _ in range(3):
        again = answer(api, rnd["session_id"], wid)
        assert again["new_found"] == []
        assert again["progress"]["found"] == 1
    # the same word answered in a later round counts nothing either
    later = api.post(
        "/api/levels/answer/",
        {"session_id": get_round(api)["session_id"], "answers": [{"word_id": wid, "correct": True}]},
        format="json",
    )
    assert later.data["progress"]["found"] == 1
    assert found_count(user) == 1


def test_found_goes_to_learned_and_leaves_missed(api, user, seeded):
    rnd = get_round(api)
    wid = rnd["words"][0]["word_id"]
    answer(api, rnd["session_id"], wid, correct=False)
    w = Word.objects.get(pk=wid)
    uw = UserWord.objects.get(user=user, word=w)
    assert uw.is_missed and not uw.is_learned
    assert found_count(user) == 0  # a miss gives no progress (and no penalty)
    answer(api, rnd["session_id"], wid, correct=True)
    uw.refresh_from_db()
    assert uw.is_learned and not uw.is_missed
    assert found_count(user) == 1


def test_answers_for_words_outside_the_round_are_ignored(api, user, seeded):
    rnd = get_round(api)
    outsider = Word.objects.filter(track="en", level="A1").exclude(id__in=[w["word_id"] for w in rnd["words"]]).first()
    data = answer(api, rnd["session_id"], outsider.id)
    assert data["ignored"] == 1 and data["progress"]["found"] == 0
    r = api.post("/api/levels/answer/", {"session_id": "nope", "word_id": outsider.id, "correct": True}, format="json")
    assert r.status_code == 404


def test_other_users_session_is_not_accepted(api, user, client_for, seeded):
    rnd = get_round(api)
    other = client_for(User.objects.create_user(email="x@example.com", password="secret123"))
    r = other.post(
        "/api/levels/answer/",
        {"session_id": rnd["session_id"], "word_id": rnd["words"][0]["word_id"], "correct": True},
        format="json",
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------- rounds
def test_round_has_no_duplicates_and_only_unfound_words(api, user, seeded):
    words = list(Word.objects.filter(track="en", level="A1").order_by("id"))
    mark_found(user, words[:80])
    found_ids = {w.id for w in words[:80]}
    for _ in range(10):
        rnd = get_round(api, size=8)
        ids = [w["word_id"] for w in rnd["words"]]
        assert len(ids) == len(set(ids)) == 8
        assert not found_ids & set(ids)  # 20 unfound left: no fillers needed
        assert not any(w["is_filler"] for w in rnd["words"])


def test_round_avoids_words_of_the_last_two_sessions(api, user, seeded):
    a = {w["word_id"] for w in get_round(api, size=20)["words"]}
    b = {w["word_id"] for w in get_round(api, size=20)["words"]}
    c = {w["word_id"] for w in get_round(api, size=20)["words"]}
    assert not a & b and not (a | b) & c  # 100 words: 60 distinct before anything repeats


def test_fillers_only_when_unfound_run_out_and_max_two_uses(api, user, seeded):
    pack = Word.objects.filter(track="en", level="A1", pack__slug="food")
    words = list(pack.order_by("id"))
    assert len(words) == 15
    mark_found(user, words[:13])
    unfound = {w.id for w in words[13:]}
    rnd = get_round(api, size=6, pack="food")
    by_filler = {w["word_id"]: w["is_filler"] for w in rnd["words"]}
    assert len(by_filler) == 6
    assert {i for i, f in by_filler.items() if not f} == unfound  # unfound always included
    fillers = [i for i, f in by_filler.items() if f]
    assert len(fillers) == 4

    before = found_count(user)
    user.refresh_from_db()
    xp_before = user.xp
    for fid in fillers:
        data = answer(api, rnd["session_id"], fid, correct=True)
        assert data["new_found"] == []
        answer(api, rnd["session_id"], fid, correct=False)  # fillers: no penalty either
    assert found_count(user) == before
    user.refresh_from_db()
    assert user.xp == xp_before
    assert not UserWord.objects.filter(user=user, word_id__in=fillers).exists()  # lists untouched
    assert set(UserLevelWord.objects.filter(user=user, word_id__in=fillers).values_list("filler_uses", flat=True)) == {
        1
    }

    # Use every filler up: no word may ever be shown as a filler more than twice.
    seen_as_filler: dict[int, int] = {}
    for _ in range(12):
        rnd = get_round(api, size=6, pack="food")
        for w in rnd["words"]:
            if w["is_filler"]:
                seen_as_filler[w["word_id"]] = seen_as_filler.get(w["word_id"], 0) + 1
                answer(api, rnd["session_id"], w["word_id"])
    totals = {r.word_id: r.filler_uses for r in UserLevelWord.objects.filter(user=user, word__in=words[:13])}
    assert max(totals.values()) <= 2
    rnd = get_round(api, size=6, pack="food")
    assert {w["word_id"] for w in rnd["words"]} == unfound  # fillers used up: smaller board
    assert all(not w["is_filler"] for w in rnd["words"])


def test_pool_done_and_level_completed(api, user, seeded):
    words = list(Word.objects.filter(track="en", level="A1"))
    food = [w for w in words if w.pack.slug == "food"]
    mark_found(user, food)
    rnd = get_round(api, pack="food")
    assert rnd["pool_done"] is True and rnd["words"] == [] and rnd["session_id"] is None
    mark_found(user, words)
    rnd = get_round(api)
    assert rnd["completed"] is True and rnd["words"] == []


def test_locked_level_round_is_forbidden(api, seeded):
    assert api.get("/api/levels/en/A2/round/").status_code == 403
    assert api.get("/api/levels/xx/A1/round/").status_code == 400
    assert api.get("/api/levels/en/A1/round/", {"game": "derdiedas"}).status_code == 400


def test_derdiedas_round_has_only_nouns(api, seeded):
    rnd = get_round(api, track="de", size=20, game="derdiedas")
    assert rnd["words"] and all(w["article"] in ("der", "die", "das") for w in rnd["words"])


# ------------------------------------------------------- progress and unlocking
@pytest.mark.parametrize("total,target", [(100, 70), (150, 105), (200, 140), (250, 175), (300, 210)])
def test_unlock_target_per_level_size(total, target):
    assert unlock_target(total) == target


def test_progress_and_unlock_for_every_level(api, user, seeded):
    levels = ["A1", "A2", "B1", "B2", "C1"]
    for i, lv in enumerate(levels[:-1]):
        words = list(Word.objects.filter(track="de", level=lv).order_by("id"))
        assert len(words) == LEVEL_SIZES[lv]
        target = unlock_target(len(words))
        mark_found(user, words[: target - 1])
        rows = {r["level"]: r for r in api.get("/api/levels/de/").data["levels"]}
        assert rows[lv]["found"] == target - 1
        assert rows[lv]["to_unlock"] == 1
        assert rows[lv]["remaining"] == len(words) - target + 1
        assert rows[levels[i + 1]]["unlocked"] is False
        mark_found(user, words[target - 1 : target])
        rows = {r["level"]: r for r in api.get("/api/levels/de/").data["levels"]}
        assert rows[lv]["percent"] == 70
        assert rows[lv]["to_unlock"] == 0
        assert rows[levels[i + 1]]["unlocked"] is True
    # English is a separate track: still only A1 open.
    en = api.get("/api/levels/en/").data["levels"]
    assert [r["unlocked"] for r in en] == [True, False, False, False, False]


def test_level_detail_lists_found_words(api, user, seeded):
    w = Word.objects.filter(track="en", level="A1").first()
    mark_found(user, [w])
    d = api.get("/api/levels/en/A1/").data
    assert d["found"] == 1 and d["total"] == 100 and d["unlock_target"] == 70
    assert [x["id"] for x in d["found_words"]] == [w.id]


def test_completion_bonus_exactly_once(api, user, seeded):
    words = list(Word.objects.filter(track="en", level="A1").order_by("id"))
    mark_found(user, words[:-1])
    rnd = get_round(api, size=3)
    last = words[-1].id
    assert last in [w["word_id"] for w in rnd["words"]]
    user.refresh_from_db()
    xp0 = user.xp
    data = answer(api, rnd["session_id"], last)
    assert data["completed_now"] is True and data["bonus_xp"] == COMPLETION_BONUS_XP
    assert data["progress"]["completed"] is True and data["progress"]["percent"] == 100
    again = answer(api, rnd["session_id"], last)
    assert again["completed_now"] is False and again["bonus_xp"] == 0
    user.refresh_from_db()
    assert user.xp == xp0 + COMPLETION_BONUS_XP
    assert LevelCompletion.objects.filter(user=user, track="en", level="A1").count() == 1
    assert UserAchievement.objects.filter(user=user, code="level_complete").exists()


# ------------------------------------------------------------ results endpoint
def test_level_results_give_xp_only_for_new_words_once(api, user, seeded):
    rnd = get_round(api, size=4)
    ids = [w["word_id"] for w in rnd["words"]]
    already = Word.objects.get(pk=ids[0])
    mark_found(user, [already])
    results = [{"term": "x", "word_id": i, "correct": True} for i in ids]
    payload = {"game": "speed", "track": "en", "source": "level", "session_id": rnd["session_id"], "results": results}
    r = api.post("/api/games/results/", payload, format="json")
    assert r.status_code == 200, r.data
    assert r.data["level_round"]["new_found_count"] == 3
    assert r.data["xp_earned"] == 3 * 4 + round(3 * 4 * 0.2)  # perfect round bonus
    retry = api.post("/api/games/results/", payload, format="json")
    assert retry.data["xp_earned"] == 0  # a retry never pays twice
    assert found_count(user) == 4
    bad = api.post("/api/games/results/", {**payload, "session_id": ""}, format="json")
    assert bad.status_code == 400


# --------------------------------------------------------------- seed + migration
def test_seed_files_exact_counts_no_duplicates():
    counts, errors = check_seed()
    assert errors == []
    for track in ("en", "de"):
        assert counts[track] == LEVEL_SIZES
        assert sum(counts[track].values()) == 1000


def test_seed_is_idempotent_and_keeps_ids(db):
    call_command("seed_words", stdout=io.StringIO())
    ids = dict(Word.objects.values_list("id", "word"))
    assert len(ids) == 2000
    call_command("seed_words", "--force", stdout=io.StringIO())
    call_command("seed_words", stdout=io.StringIO())
    assert dict(Word.objects.values_list("id", "word")) == ids
    for track in ("en", "de"):
        for lv, n in LEVEL_SIZES.items():
            assert Word.objects.filter(track=track, level=lv).count() == n


def test_migration_keeps_leitner_progress(user, seeded):
    mig = importlib.import_module("words.migrations.0002_level_progress")
    a, b = Word.objects.filter(track="en", level="A1")[:2]
    UserWord.objects.create(user=user, track="en", term_key=a.display.lower(), term=a.display, box=5, seen=True)
    UserWord.objects.create(user=user, track="en", term_key=b.display.lower(), term=b.display, box=3, seen=True)
    mig.backfill_found(apps, None)
    mig.backfill_found(apps, None)  # idempotent
    assert list(UserLevelWord.objects.filter(user=user, found_at__isnull=False).values_list("word_id", flat=True)) == [
        a.id
    ]


def test_backfill_service_marks_shown_rows_found(user, seeded):
    w = Word.objects.filter(track="de", level="A1").first()
    UserLevelWord.objects.create(user=user, word=w, track="de", level="A1")  # shown, not found
    UserWord.objects.create(user=user, track="de", term_key=w.display.lower(), term=w.display, box=5, word=w)
    assert backfill_from_leitner() == 1
    assert found_count(user, "de", "A1") == 1


def test_level_review_source_returns_found_words(api, user, seeded):
    w = Word.objects.filter(track="en", level="A1").first()
    mark_found(user, [w])
    r = api.get("/api/games/words/", {"game": "speed", "track": "en", "source": "levelreview", "level": "A1"})
    assert r.status_code == 200
    assert [i["word_id"] for i in r.data["items"]] == [w.id]
