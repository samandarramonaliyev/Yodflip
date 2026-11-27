from datetime import timedelta

from django.db.models import Count, Sum
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserSerializer
from words.models import UserWord
from words.services import due_queryset

from .models import DailyActivity, GameSession, UserAchievement
from .services import ACHIEVEMENTS, leaderboard, level_for_xp, today, xp_for_level


def profile_stats(user, track: str) -> dict:
    words = UserWord.objects.filter(user=user, track=track)
    agg = words.aggregate(c=Sum("correct_count"), m=Sum("miss_count"))
    correct, missed = agg["c"] or 0, agg["m"] or 0
    day = today()
    acts = {a.date: a for a in DailyActivity.objects.filter(user=user, date__gte=day - timedelta(days=6))}
    chart = []
    for i in range(6, -1, -1):
        d = day - timedelta(days=i)
        a = acts.get(d)
        chart.append({"date": d.isoformat(), "xp": a.xp if a else 0, "correct": a.correct if a else 0})
    level = level_for_xp(user.xp)
    return {
        "user": UserSerializer(user).data,
        "track": track,
        "xp": user.xp,
        "level": level,
        "level_floor": xp_for_level(level),
        "level_ceil": xp_for_level(level + 1),
        "streak": user.streak,
        "best_streak": user.best_streak,
        "played_today": user.last_active_date == day,
        "total_words": words.filter(seen=True).count(),
        "learned": words.filter(box__gte=5).count(),
        "missed": words.filter(box=1, miss_count__gt=0).count(),
        "want": words.filter(want_to_learn=True).count(),
        "due": due_queryset(user, track).count(),
        "accuracy": round(100 * correct / (correct + missed)) if (correct + missed) else 0,
        "cefr": user.cefr_for(track),
        "chart": chart,
        "translation_langs": translation_breakdown(user, track),
        "week": week_stats(user),
        "invited": user.invited.count(),
    }


def week_stats(user) -> dict:
    """This league week (Monday → now, both tracks): XP, words found / learned, accuracy — for the share card."""
    from datetime import datetime, time

    from django.utils import timezone

    from leagues.services import tz, week_start_for
    from words.models import UserLevelWord

    start = week_start_for()
    acts = DailyActivity.objects.filter(user=user, date__gte=start).aggregate(
        xp=Sum("xp"), c=Sum("correct"), a=Sum("attempts")
    )
    since = datetime.combine(start, time.min, tzinfo=tz())
    words = UserLevelWord.objects.filter(user=user, found_at__gte=since).count()
    attempts = acts["a"] or 0
    return {
        "start": start.isoformat(),
        "xp": acts["xp"] or 0,
        "words": words,
        "accuracy": round(100 * (acts["c"] or 0) / attempts) if attempts else 0,
        "now": timezone.now().isoformat(),
    }


def translation_breakdown(user, track: str) -> list[dict]:
    """Share of memorization games per translation language, e.g. UZ 60%, RU 30%, DE 10%."""
    rows = (
        GameSession.objects.filter(user=user, track=track)
        .exclude(translation_lang="")
        .values("translation_lang")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    total = sum(r["n"] for r in rows)
    return [{"lang": r["translation_lang"], "count": r["n"], "percent": round(100 * r["n"] / total)} for r in rows]


class ProfileStatsView(APIView):
    @extend_schema(parameters=[OpenApiParameter("track", str)], responses={200: dict})
    def get(self, request):
        track = request.query_params.get("track") or request.user.active_track
        if track not in ("en", "de"):
            track = "en"
        return Response(profile_stats(request.user, track))


class AchievementsView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        mine = {a.code: a.created_at for a in UserAchievement.objects.filter(user=request.user)}
        return Response(
            [
                {"code": code, "emoji": emoji, "unlocked": code in mine, "unlocked_at": mine.get(code)}
                for code, emoji in ACHIEVEMENTS.items()
            ]
        )


class LeaderboardView(APIView):
    @extend_schema(parameters=[OpenApiParameter("period", str, enum=["weekly", "all"])], responses={200: dict})
    def get(self, request):
        period = request.query_params.get("period", "weekly")
        if period not in ("weekly", "all"):
            period = "weekly"
        return Response(leaderboard(period, me=request.user))
