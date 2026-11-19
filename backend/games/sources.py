"""Word sources for games: built-in levels, decks, scanned sets, the user's lists, review, daily."""

from __future__ import annotations

import random
from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from decks.models import Deck, WordSet
from words.models import UserWord, Word
from words.services import LEVELS, is_level_unlocked, list_queryset

from .rules import ARTICLE, item_usable

DAILY_COUNT = 10


def item_from_word(w: Word) -> dict:
    return {
        "key": f"w{w.id}",
        "word_id": w.id,
        "term": w.display,
        "word": w.word,
        "article": w.article,
        "definition": w.definition,
        "translation": w.translation_uz,
        "pos": w.part_of_speech,
        "example": w.example,
        "example_uz": w.example_uz,
    }


def _split_article(term: str, article: str) -> tuple[str, str]:
    parts = term.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in ("der", "die", "das"):
        return parts[1], parts[0].lower()
    return term, article


def item_from_card(c) -> dict:
    word, article = _split_article(c.term, c.article)
    term = f"{article} {word}" if article else word
    return {
        "key": f"c{c.id}",
        "word_id": None,
        "term": term,
        "word": word,
        "article": article,
        "definition": c.definition,
        "translation": c.translation,
        "pos": "",
        "example": c.example,
        "example_uz": "",
    }


def item_from_pair(p) -> dict:
    word, article = _split_article(p.word, p.article)
    term = f"{article} {word}" if article else word
    return {
        "key": f"p{p.id}",
        "word_id": None,
        "term": term,
        "word": word,
        "article": article,
        "definition": p.definition,
        "translation": p.translation_uz,
        "pos": p.part_of_speech,
        "example": "",
        "example_uz": "",
    }


def item_from_userword(uw: UserWord) -> dict:
    word, article = _split_article(uw.term, uw.article)
    return {
        "key": f"u{uw.id}",
        "word_id": uw.word_id,
        "term": uw.term,
        "word": word,
        "article": article,
        "definition": uw.definition,
        "translation": uw.translation_uz,
        "pos": "",
        "example": "",
        "example_uz": "",
    }


def daily_words(track: str, day: date) -> list[Word]:
    """The same 10 words for every user, per track, per day (deterministic)."""
    ids = list(
        Word.objects.filter(track=track, level__in=["A1", "A2", "B1", "B2"]).order_by("id").values_list("id", flat=True)
    )
    if not ids:
        return []
    rng = random.Random(f"wordflip-daily-{track}-{day.isoformat()}")
    chosen = rng.sample(ids, min(DAILY_COUNT, len(ids)))
    by_id = Word.objects.in_bulk(chosen)
    return [by_id[i] for i in chosen if i in by_id]


def get_items(user, track: str, source: str, params: dict, mode: str, day: date | None = None) -> list[dict]:
    if source == "level":
        level = params.get("level")
        if level not in LEVELS:
            raise ValidationError({"level": "invalid_level"})
        if not is_level_unlocked(user, track, level):
            raise PermissionDenied("level_locked")
        qs = Word.objects.filter(track=track, level=level)
        if params.get("pack"):
            qs = qs.filter(pack__slug=params["pack"])
        items = [item_from_word(w) for w in qs]
    elif source == "deck":
        deck = get_object_or_404(Deck, pk=params.get("id"))
        if deck.owner_id != user.id and not deck.is_public:
            raise PermissionDenied("not_your_deck")
        if deck.track != track:
            raise ValidationError({"track": "track_mismatch"})
        items = [item_from_card(c) for c in deck.cards.all()]
    elif source == "set":
        ws = get_object_or_404(WordSet, pk=params.get("id"), owner=user)
        if ws.track != track:
            raise ValidationError({"track": "track_mismatch"})
        items = [item_from_pair(p) for p in ws.pairs.all()]
    elif source in ("missed", "want", "learned", "review"):
        which = "due" if source == "review" else source
        items = [item_from_userword(uw) for uw in list_queryset(user, track, which).order_by("due_at")[:200]]
    elif source == "daily":
        from gamification.services import today

        return [item_from_word(w) for w in daily_words(track, day or today())]
    else:
        raise ValidationError({"source": "invalid_source"})

    items = [i for i in items if item_usable(i, mode)]
    if mode == ARTICLE and track != "de":
        return []
    return items
