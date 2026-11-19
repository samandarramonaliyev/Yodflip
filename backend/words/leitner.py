"""Leitner spaced-repetition (5 boxes).

* correct  -> move up one box (max 5)
* miss     -> back to box 1
* Learned  = box 5
* Missed   = box 1 with at least one miss
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MIN_BOX = 1
MAX_BOX = 5
# Days until the word is due again after landing in a box.
INTERVAL_DAYS = {1: 0, 2: 1, 3: 3, 4: 7, 5: 14}


@dataclass
class LeitnerState:
    box: int = MIN_BOX
    correct_count: int = 0
    miss_count: int = 0

    @property
    def learned(self) -> bool:
        return self.box >= MAX_BOX

    @property
    def missed(self) -> bool:
        return self.box == MIN_BOX and self.miss_count > 0


def next_box(box: int, correct: bool) -> int:
    if not correct:
        return MIN_BOX
    return min(MAX_BOX, max(MIN_BOX, box) + 1)


def due_after(box: int, now: datetime) -> datetime:
    return now + timedelta(days=INTERVAL_DAYS.get(box, 0))


def apply(state: LeitnerState, correct: bool) -> LeitnerState:
    return LeitnerState(
        box=next_box(state.box, correct),
        correct_count=state.correct_count + (1 if correct else 0),
        miss_count=state.miss_count + (0 if correct else 1),
    )


def apply_to_userword(uw, correct: bool, now: datetime) -> bool:
    """Mutate a UserWord in place. Returns True if the word just became Learned."""
    was_learned = uw.box >= MAX_BOX
    st = apply(LeitnerState(uw.box, uw.correct_count, uw.miss_count), correct)
    uw.box, uw.correct_count, uw.miss_count = st.box, st.correct_count, st.miss_count
    uw.seen = True
    uw.last_seen_at = now
    uw.due_at = due_after(uw.box, now)
    return st.learned and not was_learned
