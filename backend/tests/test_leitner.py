from datetime import UTC, datetime, timedelta

import pytest

from words import leitner
from words.leitner import LeitnerState, apply, next_box
from words.models import UserWord
from words.services import list_queryset, record_answer


def test_correct_moves_up_one_box():
    assert next_box(1, True) == 2
    assert next_box(4, True) == 5


def test_box_is_capped_at_five():
    assert next_box(5, True) == 5


def test_miss_sends_back_to_box_one():
    for b in range(1, 6):
        assert next_box(b, False) == 1


def test_learned_and_missed_flags():
    s = LeitnerState()
    for _ in range(4):
        s = apply(s, True)
    assert s.box == 5 and s.learned and not s.missed
    s = apply(s, False)
    assert s.box == 1 and s.missed and s.miss_count == 1 and s.correct_count == 4


def test_new_word_is_not_missed():
    assert not LeitnerState().missed


def test_due_interval_grows():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert leitner.due_after(1, now) == now
    assert leitner.due_after(5, now) == now + timedelta(days=14)


@pytest.mark.django_db
def test_record_answer_and_lists(user):
    item = {"term": "apple", "translation": "olma", "definition": "a fruit"}
    record_answer(user, "en", item, False)
    assert list_queryset(user, "en", "missed").count() == 1
    for _ in range(4):
        _, became = record_answer(user, "en", item, True)
    assert became is True  # 4th correct answer reaches box 5
    uw = UserWord.objects.get(user=user, term_key="apple")
    assert uw.box == 5
    assert list_queryset(user, "en", "learned").count() == 1
    assert list_queryset(user, "en", "missed").count() == 0
    # tracks never mix
    assert list_queryset(user, "de", "learned").count() == 0


@pytest.mark.django_db
def test_terms_are_case_insensitive(user):
    record_answer(user, "en", {"term": "Apple"}, True)
    record_answer(user, "en", {"term": " apple "}, True)
    assert UserWord.objects.filter(user=user).count() == 1
    assert UserWord.objects.get(user=user).box == 3
