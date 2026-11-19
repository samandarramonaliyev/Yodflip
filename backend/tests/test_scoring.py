from games.rules import (
    ARTICLE,
    DEFINITION,
    MEMORIZE,
    allowed_for_track,
    back_side,
    item_usable,
    mode_for,
)
from games.scoring import daily_score, match_round_score, session_xp
from gamification.services import level_for_xp, xp_for_level


def test_match_perfect_round():
    r = match_round_score(pairs=6, misses=0)
    assert r.accuracy == 100
    assert r.flips == 12
    assert r.perfect
    assert r.xp == 60 + 30


def test_match_with_misses():
    r = match_round_score(pairs=4, misses=4)
    assert r.accuracy == 50
    assert r.flips == 16
    assert not r.perfect
    assert r.xp == 40


def test_match_empty_round():
    r = match_round_score(0, 0)
    assert r.xp == 0 and r.accuracy == 0 and not r.perfect


def test_session_xp_perfect_bonus_and_cap():
    xp, perfect = session_xp("speed", 10, 10, combo_max=50)
    assert perfect and xp == 40 + 8 + 20
    xp, _ = session_xp("match", 1000, 1000)
    assert xp == 400


def test_daily_score_prefers_fast_and_correct():
    assert daily_score(10, 30_000) > daily_score(10, 90_000)
    assert daily_score(10, 200_000) >= daily_score(9, 10_000)
    assert daily_score(0, 1000) == 0


def test_level_curve():
    assert level_for_xp(0) == 1
    assert level_for_xp(99) == 1
    assert level_for_xp(100) == 2
    assert level_for_xp(300) == 3
    assert xp_for_level(4) == 600


def test_game_direction_rules():
    assert mode_for("match") == DEFINITION
    for g in ("speed", "builder", "falling", "review", "daily", "flashcards", "learn", "write", "memory"):
        assert mode_for(g) == MEMORIZE
    assert mode_for("derdiedas") == ARTICLE
    assert not allowed_for_track("derdiedas", "en")
    assert allowed_for_track("derdiedas", "de")
    item = {"term": "apple", "definition": "a round fruit", "translation": "olma", "article": ""}
    assert back_side(item, DEFINITION) == "a round fruit"
    assert back_side(item, MEMORIZE) == "olma"
    assert not item_usable(item, ARTICLE)
    assert not item_usable({**item, "definition": ""}, DEFINITION)
