import random

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import TRACK_CHOICES
from gamification.models import GameSession
from gamification.services import check_achievements, level_for_xp, record_activity, today
from words.services import record_answer

from .models import DailyChallengeScore
from .rules import GAMES, allowed_for_track, mode_for
from .scoring import daily_score, match_round_score, session_xp
from .sources import get_items


class ResultItemSerializer(serializers.Serializer):
    term = serializers.CharField(max_length=200)
    word_id = serializers.IntegerField(required=False, allow_null=True)
    translation = serializers.CharField(max_length=300, required=False, allow_blank=True)
    definition = serializers.CharField(max_length=500, required=False, allow_blank=True)
    article = serializers.CharField(max_length=3, required=False, allow_blank=True)
    correct = serializers.BooleanField()


class ResultsSerializer(serializers.Serializer):
    game = serializers.ChoiceField(choices=list(GAMES))
    track = serializers.ChoiceField(choices=TRACK_CHOICES)
    source = serializers.CharField(max_length=40, required=False, allow_blank=True)
    results = ResultItemSerializer(many=True)
    duration_ms = serializers.IntegerField(min_value=0, required=False, default=0)
    combo_max = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate_results(self, value):
        if len(value) > 300:
            raise serializers.ValidationError("too_many_results")
        return value


class WordsView(APIView):
    """Items for a game. Content side is chosen by the Game Direction Rules."""

    @extend_schema(
        parameters=[
            OpenApiParameter("game", str, enum=list(GAMES)),
            OpenApiParameter("track", str, enum=["en", "de"]),
            OpenApiParameter(
                "source", str, enum=["level", "deck", "set", "missed", "want", "learned", "review", "daily"]
            ),
            OpenApiParameter("level", str),
            OpenApiParameter("pack", str),
            OpenApiParameter("id", int),
            OpenApiParameter("limit", int),
        ],
        responses={200: dict},
    )
    def get(self, request):
        p = request.query_params
        game = p.get("game", "match")
        track = p.get("track") or request.user.active_track
        if game not in GAMES or track not in ("en", "de"):
            raise ValidationError({"detail": "invalid_game_or_track"})
        if not allowed_for_track(game, track):
            raise ValidationError({"detail": "game_not_available_for_track"})
        mode = mode_for(game)
        items = get_items(request.user, track, p.get("source", "level"), p, mode)
        if p.get("source") != "daily":
            random.shuffle(items)
        try:
            limit = max(1, min(int(p.get("limit", 200)), 200))
        except ValueError:
            limit = 200
        items = items[:limit]
        payload = {"game": game, "track": track, "mode": mode, "items": items}
        if p.get("source") == "daily":
            done = DailyChallengeScore.objects.filter(user=request.user, track=track, date=today()).first()
            payload["already_played"] = bool(done)
            payload["my_score"] = done.score if done else None
        return Response(payload)


class ResultsView(APIView):
    """Submit a finished game: updates Leitner boxes, XP, streak, achievements."""

    @extend_schema(request=ResultsSerializer, responses={200: dict})
    def post(self, request):
        ser = ResultsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = request.user
        game, track = d["game"], d["track"]
        if not allowed_for_track(game, track):
            raise ValidationError({"detail": "game_not_available_for_track"})
        results = d["results"]
        attempts = len(results)
        correct = sum(1 for r in results if r["correct"])
        learned_now = []
        with transaction.atomic():
            for r in results:
                uw, became = record_answer(user, track, r, r["correct"])
                if became:
                    learned_now.append(uw.term)
            xp, perfect = session_xp(game, correct, attempts, d.get("combo_max", 0))
            daily_payload = None
            if game == "daily":
                score = daily_score(correct, d["duration_ms"])
                obj, created = DailyChallengeScore.objects.get_or_create(
                    user=user,
                    track=track,
                    date=today(),
                    defaults={"correct": correct, "duration_ms": d["duration_ms"], "score": score},
                )
                if not created:
                    xp = 0  # replays of the daily challenge don't give XP
                daily_payload = {"score": obj.score, "first_attempt": created}
            GameSession.objects.create(
                user=user,
                track=track,
                game=game,
                mode=GAMES[game],
                source=d.get("source", ""),
                xp=xp,
                correct=correct,
                attempts=attempts,
                duration_ms=d["duration_ms"],
            )
            record_activity(user, xp, correct, attempts)
            new_achievements = check_achievements(user, perfect=perfect, daily=game == "daily")
        resp = {
            "xp_earned": xp,
            "xp_total": user.xp,
            "level": level_for_xp(user.xp),
            "streak": user.streak,
            "correct": correct,
            "attempts": attempts,
            "accuracy": round(100 * correct / attempts) if attempts else 0,
            "perfect": perfect,
            "learned_now": learned_now,
            "new_achievements": new_achievements,
        }
        if game == "match":
            r = match_round_score(correct, attempts - correct)
            resp["flips"] = r.flips
        if daily_payload:
            resp["daily"] = daily_payload
        return Response(resp, status=status.HTTP_200_OK)


class DailyLeaderboardView(APIView):
    @extend_schema(parameters=[OpenApiParameter("track", str, enum=["en", "de"])], responses={200: dict})
    def get(self, request):
        track = request.query_params.get("track") or request.user.active_track
        rows = DailyChallengeScore.objects.filter(track=track, date=today()).select_related("user")[:100]
        entries = [
            {
                "rank": i + 1,
                "name": r.user.display_name,
                "avatar_url": r.user.avatar_url,
                "telegram_username": r.user.telegram_username,
                "is_telegram": r.user.telegram_id is not None,
                "score": r.score,
                "correct": r.correct,
                "duration_ms": r.duration_ms,
                "is_me": r.user_id == request.user.id,
            }
            for i, r in enumerate(rows)
        ]
        return Response({"track": track, "date": today().isoformat(), "entries": entries})
