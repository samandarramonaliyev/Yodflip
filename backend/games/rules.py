"""Game Direction Rules (strict).

1. DEFINITION games: word ↔ same-language definition. Never Uzbek.
2. MEMORIZATION games: word ↔ Uzbek translation (reverse toggle allowed).
3. ARTICLE game (Der·Die·Das): German nouns → article. German track only.
"""

DEFINITION = "definition"
MEMORIZE = "memorize"
ARTICLE = "article"

GAMES: dict[str, str] = {
    "match": DEFINITION,
    "speed": MEMORIZE,
    "builder": MEMORIZE,
    "falling": MEMORIZE,
    "review": MEMORIZE,
    "daily": MEMORIZE,
    "flashcards": MEMORIZE,
    "learn": MEMORIZE,
    "write": MEMORIZE,
    "memory": MEMORIZE,  # Memory Pairs (our extra game): word ↔ Uzbek, classic concentration
    "derdiedas": ARTICLE,
}

# Base XP per correct answer, per game.
XP_PER_CORRECT: dict[str, int] = {
    "match": 10,
    "speed": 4,
    "builder": 8,
    "falling": 5,
    "review": 6,
    "daily": 10,
    "flashcards": 2,
    "learn": 5,
    "write": 8,
    "memory": 6,
    "derdiedas": 3,
}
SESSION_XP_CAP = 400


def mode_for(game: str, requested: str | None = None) -> str:
    """Resolve the content mode for a game. Built-in levels may be played in either mode
    by choosing a game; a game's own mode always wins (match is always definition)."""
    if game not in GAMES:
        raise ValueError("unknown_game")
    return GAMES[game]


def allowed_for_track(game: str, track: str) -> bool:
    if game == "derdiedas":
        return track == "de"
    return track in ("en", "de")


def item_usable(item: dict, mode: str) -> bool:
    """An item can be used in a mode only if it has the needed back side."""
    if mode == DEFINITION:
        return bool(item.get("definition"))
    if mode == MEMORIZE:
        return bool(item.get("translation"))
    if mode == ARTICLE:
        return item.get("article") in ("der", "die", "das")
    return False


def back_side(item: dict, mode: str) -> str:
    if mode == DEFINITION:
        return item["definition"]
    if mode == MEMORIZE:
        return item["translation"]
    return item["article"]
