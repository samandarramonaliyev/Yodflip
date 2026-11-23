from __future__ import annotations

from datetime import date, timedelta

from django.db.models import F, Sum
from django.utils import timezone

# code -> (emoji, condition description key). Titles are translated on the frontend.
ACHIEVEMENTS: dict[str, str] = {
    "first_game": "🎮",
    "first_scan": "📸",
    "first_deck": "🗂️",
    "perfect_round": "💯",
    "streak_3": "🔥",
    "streak_7": "🏆",
    "streak_30": "👑",
    "words_10": "🌱",
    "words_100": "🌳",
    "words_500": "🧠",
    "xp_1000": "⭐",
    "daily_first": "📅",
    "polyglot": "🌍",
    "deck_master": "🃏",
    "level_complete": "🎓",
    "first_duel": "⚔️",
    "duel_wins_10": "🥇",
    "invited_5": "🤝",
}


def level_for_xp(xp: int) -> int:
    """Level L needs 50·L·(L−1) XP: L1=0, L2=100, L3=300, L4=600, ..."""
    level = 1
    while 50 * (level + 1) * level <= xp:
        level += 1
    return level


def xp_for_level(level: int) -> int:
    return 50 * level * (level - 1)


def today() -> date:
    return timezone.localdate()


def update_streak(user, day: date | None = None) -> None:
    day = day or today()
    if user.last_active_date == day:
        return
    if user.last_active_date == day - timedelta(days=1):
        user.streak += 1
    else:
        user.streak = 1
    user.best_streak = max(user.best_streak, user.streak)
    user.last_active_date = day


def record_activity(user, xp: int, correct: int, attempts: int, games: int = 1) -> None:
    from .models import DailyActivity

    day = today()
    act, _ = DailyActivity.objects.get_or_create(user=user, date=day)
    DailyActivity.objects.filter(pk=act.pk).update(
        xp=F("xp") + xp,
        correct=F("correct") + correct,
        attempts=F("attempts") + attempts,
        games=F("games") + games,
    )
    update_streak(user, day)
    user.xp += xp
    user.save(update_fields=["xp", "streak", "best_streak", "last_active_date"])


def add_xp(user, xp: int) -> None:
    """XP that is not a play of the user right now (e.g. a duel the opponent just finished): no streak change."""
    from .models import DailyActivity

    act, _ = DailyActivity.objects.get_or_create(user=user, date=today())
    DailyActivity.objects.filter(pk=act.pk).update(xp=F("xp") + xp)
    type(user).objects.filter(pk=user.pk).update(xp=F("xp") + xp)
    user.refresh_from_db(fields=["xp"])


def grant(user, code: str) -> bool:
    from .models import UserAchievement

    if code not in ACHIEVEMENTS:
        return False
    _, created = UserAchievement.objects.get_or_create(user=user, code=code)
    return created


def check_achievements(user, *, perfect: bool = False, daily: bool = False) -> list[str]:
    from decks.models import Deck
    from words.models import UserWord

    from .models import GameSession

    new: list[str] = []

    def g(code):
        if grant(user, code):
            new.append(code)

    if GameSession.objects.filter(user=user).exists():
        g("first_game")
    if perfect:
        g("perfect_round")
    if daily:
        g("daily_first")
    for n in (3, 7, 30):
        if user.streak >= n:
            g(f"streak_{n}")
    learned = UserWord.objects.filter(user=user, box__gte=5).count()
    for n in (10, 100, 500):
        if learned >= n:
            g(f"words_{n}")
    if user.xp >= 1000:
        g("xp_1000")
    if GameSession.objects.filter(user=user).values("track").distinct().count() >= 2:
        g("polyglot")
    if Deck.objects.filter(owner=user).count() >= 5:
        g("deck_master")
    return new


def award_event(user, event: str) -> list[str]:
    mapping = {"scan": "first_scan", "deck_created": "first_deck"}
    code = mapping.get(event)
    new = [code] if code and grant(user, code) else []
    if event == "deck_created":
        new += [c for c in check_achievements(user) if c == "deck_master"]
    return new


def week_start(day: date | None = None) -> date:
    day = day or today()
    return day - timedelta(days=day.weekday())


def leaderboard(period: str, limit: int = 50, me=None) -> dict:
    from accounts.models import User

    from .models import DailyActivity

    if period == "weekly":
        rows = (
            DailyActivity.objects.filter(date__gte=week_start())
            .values("user_id")
            .annotate(score=Sum("xp"))
            .filter(score__gt=0)
            .order_by("-score")
        )
        ranked = list(rows[: max(limit, 500)])
        users = {u.id: u for u in User.objects.filter(id__in=[r["user_id"] for r in ranked])}
        entries = [(users[r["user_id"]], r["score"]) for r in ranked if r["user_id"] in users]
    else:
        entries = [(u, u.xp) for u in User.objects.filter(xp__gt=0).order_by("-xp")[: max(limit, 500)]]

    def row(rank, u, score):
        return {
            "rank": rank,
            "user_id": u.id,
            "name": u.display_name or "—",
            "telegram_username": u.telegram_username,
            "avatar_url": u.avatar_url,
            "is_telegram": u.telegram_id is not None,
            "score": score,
            "level": level_for_xp(u.xp),
            "streak": u.streak,
        }

    out = [row(i + 1, u, s) for i, (u, s) in enumerate(entries[:limit])]
    my = None
    if me is not None:
        for i, (u, s) in enumerate(entries):
            if u.id == me.id:
                my = row(i + 1, u, s)
                break
    return {"period": period, "entries": out, "me": my}
