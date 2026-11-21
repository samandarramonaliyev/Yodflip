"""Level progress API (/api/levels/...)."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import levels
from .models import LevelRound
from .serializers import WordSerializer


def _check(track: str, level: str | None = None) -> None:
    if track not in ("en", "de"):
        raise ValidationError({"track": "invalid_track"})
    if level is not None and level not in levels.LEVELS:
        raise ValidationError({"level": "invalid_level"})


def round_item(w, is_filler: bool) -> dict:
    from games.sources import item_from_word

    return {**item_from_word(w), "is_filler": is_filler}


class TrackProgressView(APIView):
    """Progress of every level of a track (found / total / percent / unlocked / completed)."""

    @extend_schema(responses={200: dict})
    def get(self, request, track: str):
        _check(track)
        return Response({"track": track, "levels": levels.progress(request.user, track, with_packs=True)})


class LevelDetailView(APIView):
    """Progress of one level + the list of found words."""

    @extend_schema(responses={200: dict})
    def get(self, request, track: str, level: str):
        _check(track, level)
        row = levels.level_progress(request.user, track, level)
        found = WordSerializer(levels.found_words(request.user, track, level), many=True).data
        return Response({"track": track, **row, "found_words": found})


class RoundView(APIView):
    """Build a round on the server: unfound words first, fillers only when needed."""

    @extend_schema(
        parameters=[
            OpenApiParameter("size", int),
            OpenApiParameter("game", str),
            OpenApiParameter("pack", str),
        ],
        responses={200: dict},
    )
    def get(self, request, track: str, level: str):
        _check(track, level)
        if not levels.is_unlocked(request.user, track, level):
            raise PermissionDenied("level_locked")
        try:
            size = int(request.query_params.get("size", 6))
        except ValueError:
            size = 6
        game = request.query_params.get("game", "") or ""
        if game == "derdiedas" and track != "de":
            raise ValidationError({"detail": "game_not_available_for_track"})
        rnd = levels.build_round(
            request.user, track, level, size, game=game, pack=request.query_params.get("pack", "") or ""
        )
        return Response(
            {
                "session_id": rnd.session_id,
                "track": track,
                "level": level,
                "completed": rnd.completed,
                "pool_done": rnd.pool_done,
                "words": [round_item(w, w.id in rnd.filler_ids) for w in rnd.words],
                "progress": levels.level_progress(request.user, track, level),
            }
        )


class AnswerItemSerializer(serializers.Serializer):
    word_id = serializers.IntegerField()
    correct = serializers.BooleanField()


class AnswerSerializer(serializers.Serializer):
    """Either one answer ({session_id, word_id, correct}) or a batch ({session_id, answers: [...]})."""

    session_id = serializers.CharField(max_length=40)
    word_id = serializers.IntegerField(required=False)
    correct = serializers.BooleanField(required=False)
    answers = AnswerItemSerializer(many=True, required=False)

    def validate(self, attrs):
        items = [(a["word_id"], a["correct"]) for a in attrs.get("answers") or []]
        if "word_id" in attrs:
            if "correct" not in attrs:
                raise serializers.ValidationError({"correct": "required"})
            items.insert(0, (attrs["word_id"], attrs["correct"]))
        if not items:
            raise serializers.ValidationError({"answers": "empty"})
        if len(items) > 300:
            raise serializers.ValidationError({"answers": "too_many"})
        attrs["items"] = items
        return attrs


class AnswerView(APIView):
    """Idempotent: the first correct answer marks a word found; repeats change nothing."""

    @extend_schema(request=AnswerSerializer, responses={200: dict})
    def post(self, request):
        ser = AnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        rnd = get_object_or_404(LevelRound, session_id=ser.validated_data["session_id"], user=request.user)
        return Response(levels.record_answers(request.user, rnd, ser.validated_data["items"]))
