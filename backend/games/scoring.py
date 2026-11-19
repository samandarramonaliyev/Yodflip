"""Pure scoring functions (unit-tested)."""

from __future__ import annotations

from dataclasses import dataclass

from .rules import SESSION_XP_CAP, XP_PER_CORRECT


@dataclass
class MatchRoundScore:
    pairs: int
    misses: int
    flips: int
    accuracy: int  # percent
    xp: int
    perfect: bool


def match_round_score(pairs: int, misses: int) -> MatchRoundScore:
    """Match Game: 10 XP per matched pair, +50% bonus for a perfect round.

    Each turn flips 2 cards, so flips = 2 × (pairs + misses).
    Accuracy = pairs / (pairs + misses).
    """
    pairs = max(0, pairs)
    misses = max(0, misses)
    turns = pairs + misses
    accuracy = round(100 * pairs / turns) if turns else 0
    base = XP_PER_CORRECT["match"] * pairs
    perfect = pairs > 0 and misses == 0
    bonus = base // 2 if perfect else 0
    return MatchRoundScore(pairs, misses, 2 * turns, accuracy, min(SESSION_XP_CAP, base + bonus), perfect)


def session_xp(game: str, correct: int, attempts: int, combo_max: int = 0) -> tuple[int, bool]:
    """Generic memorization scoring. Returns (xp, perfect)."""
    if game == "match":
        r = match_round_score(correct, max(0, attempts - correct))
        return r.xp, r.perfect
    per = XP_PER_CORRECT.get(game, 5)
    base = per * max(0, correct)
    perfect = correct >= 4 and correct == attempts
    bonus = round(base * 0.2) if perfect else 0
    combo_bonus = min(combo_max, 20) if game == "speed" else 0
    return min(SESSION_XP_CAP, base + bonus + combo_bonus), perfect


def daily_score(correct: int, duration_ms: int, total: int = 10) -> int:
    """Daily Challenge leaderboard score: 100 per correct answer + up to 300 speed bonus."""
    if correct <= 0:
        return 0
    seconds = max(0, duration_ms) / 1000
    speed_bonus = max(0, round(300 - seconds * 3)) if correct == total else max(0, round(90 - seconds))
    return correct * 100 + speed_bonus
