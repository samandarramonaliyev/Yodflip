"""Pick and freeze the 10 questions of a duel (same words, order and options for both players)."""

from __future__ import annotations

import random

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from decks.models import Deck
from games.rules import item_usable, mode_for
from games.sources import get_items, item_from_card, item_from_word
from words.models import Word
from words.translations import apply_translations, resolve

WORDS = 10
OPTIONS = 4
MATCH_BOARD = 5  # Match duels are two boards of 5 words and 5 definitions


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def load_items(user, *, track: str, source: str, ref: str, mode: str, lang: str, trusted: bool = False):
    """(items, label, translation language). `trusted` skips ownership / lock checks (rematch)."""
    game_mode = mode_for(mode)
    if source == "deck":
        if not str(ref).isdigit():
            raise ValidationError({"source_ref": "invalid_deck"})
        qs = Deck.objects.all() if trusted else Deck.objects.filter(owner=user)
        deck = get_object_or_404(qs, pk=int(ref))
        if deck.track != track:
            raise ValidationError({"track": "track_mismatch"})
        items = [item_from_card(c) for c in deck.cards.select_related("deck")]
        return [i for i in items if item_usable(i, game_mode)], deck.name, deck.translation_lang
    lang, _ = resolve(track, lang)
    if source == "level":
        if trusted:
            words = Word.objects.filter(track=track, level=ref).exclude(level="")
            items = apply_translations([item_from_word(w) for w in words], lang)
            items = [i for i in items if item_usable(i, game_mode)]
        else:
            items = get_items(user, track, "level", {"level": ref}, game_mode, translation_lang=lang)
        return items, ref, lang
    raise ValidationError({"source": "invalid_source"})


def build_questions(items: list[dict], mode: str, rng: random.Random | None = None) -> list[dict]:
    """Frozen questions; raises when there are not enough different words."""
    rng = rng or random.SystemRandom()
    back = "definition" if mode == "match" else "translation"
    pool, seen_terms, seen_backs = [], set(), set()
    shuffled = list(items)
    rng.shuffle(shuffled)
    for i in shuffled:
        if _norm(i["term"]) in seen_terms or _norm(i[back]) in seen_backs:
            continue
        seen_terms.add(_norm(i["term"]))
        seen_backs.add(_norm(i[back]))
        pool.append(i)
    if len(pool) < WORDS:
        raise ValidationError({"detail": "not_enough_words"})
    chosen = pool[:WORDS]
    out = []
    boards: dict[int, list[str]] = {}
    for n, item in enumerate(chosen):
        answer = item[back]
        if mode == "match":
            b = n // MATCH_BOARD
            if b not in boards:
                boards[b] = [c[back] for c in chosen[b * MATCH_BOARD : (b + 1) * MATCH_BOARD]]
                rng.shuffle(boards[b])
            options = boards[b]
        else:
            options = [answer, *rng.sample([p[back] for p in pool if p is not item], OPTIONS - 1)]
            rng.shuffle(options)
        keep = ("term", "article", "definition", "translation", "translation_lang")
        out.append(
            {
                "prompt": item["term"],
                "options": list(options),
                "answer": options.index(answer),
                "item": {k: item.get(k) or "" for k in keep} | {"word_id": item.get("word_id")},
            }
        )
    return out


def public_questions(duel) -> list[dict]:
    """What a player sees: never the answer index."""
    return [
        {"index": n, "prompt": q["prompt"], "options": q["options"]}
        | ({"board": n // MATCH_BOARD} if duel.mode == "match" else {})
        for n, q in enumerate(duel.words)
    ]
