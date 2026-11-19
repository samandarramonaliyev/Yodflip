from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import leitner
from .models import UserWord, Word
from .serializers import MoveSerializer, UserWordSerializer, WantSerializer, WordSerializer
from .services import LEVELS, level_overview, list_queryset, upsert_userword

TRACK_PARAM = OpenApiParameter("track", str, enum=["en", "de"])


def get_track(request) -> str:
    body_track = request.data.get("track") if isinstance(request.data, dict) else None
    track = request.query_params.get("track") or body_track or request.user.active_track
    if track not in ("en", "de"):
        raise ValidationError({"track": "invalid_track"})
    return track


class LevelsView(APIView):
    @extend_schema(parameters=[TRACK_PARAM], responses={200: dict})
    def get(self, request):
        track = get_track(request)
        return Response({"track": track, "levels": level_overview(request.user, track)})


class LevelWordsView(APIView):
    @extend_schema(parameters=[TRACK_PARAM, OpenApiParameter("pack", str)], responses={200: WordSerializer(many=True)})
    def get(self, request, level: str):
        track = get_track(request)
        if level not in LEVELS:
            raise ValidationError({"level": "invalid_level"})
        qs = Word.objects.filter(track=track, level=level).select_related("pack")
        if request.query_params.get("pack"):
            qs = qs.filter(pack__slug=request.query_params["pack"])
        return Response(WordSerializer(qs, many=True).data)


class SearchView(APIView):
    @extend_schema(parameters=[TRACK_PARAM, OpenApiParameter("q", str)], responses={200: WordSerializer(many=True)})
    def get(self, request):
        track = get_track(request)
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response([])
        qs = (
            Word.objects.filter(track=track)
            .filter(Q(word__icontains=q) | Q(translation_uz__icontains=q) | Q(definition__icontains=q))
            .select_related("pack")[:30]
        )
        return Response(WordSerializer(qs, many=True).data)


class ListView(APIView):
    """The three profile lists: learned / missed / want (per track)."""

    @extend_schema(parameters=[TRACK_PARAM, OpenApiParameter("q", str)], responses={200: UserWordSerializer(many=True)})
    def get(self, request, which: str):
        if which not in ("learned", "missed", "want", "due"):
            raise ValidationError({"list": "invalid_list"})
        track = get_track(request)
        qs = list_queryset(request.user, track, which)
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(term__icontains=q) | Q(translation_uz__icontains=q))
        return Response(UserWordSerializer(qs.order_by("-last_seen_at", "-created_at")[:500], many=True).data)


class WantView(APIView):
    """Save a word to Want-to-learn from any game, deck or search."""

    @extend_schema(request=WantSerializer, responses={201: UserWordSerializer})
    def post(self, request):
        ser = WantSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        word = Word.objects.filter(pk=d.get("word_id"), track=d["track"]).first() if d.get("word_id") else None
        uw = upsert_userword(
            request.user,
            d["track"],
            d["term"],
            translation_uz=d.get("translation_uz", ""),
            definition=d.get("definition", ""),
            article=d.get("article", ""),
            word=word,
        )
        uw.want_to_learn = True
        uw.save()
        return Response(UserWordSerializer(uw).data, status=status.HTTP_201_CREATED)


class BulkWantView(APIView):
    @extend_schema(request=WantSerializer(many=True), responses={200: dict})
    def post(self, request):
        ser = WantSerializer(data=request.data, many=True)
        ser.is_valid(raise_exception=True)
        for d in ser.validated_data:
            uw = upsert_userword(
                request.user,
                d["track"],
                d["term"],
                translation_uz=d.get("translation_uz", ""),
                definition=d.get("definition", ""),
                article=d.get("article", ""),
            )
            uw.want_to_learn = True
            uw.save()
        return Response({"added": len(ser.validated_data)})


class UserWordDetailView(APIView):
    @extend_schema(request=MoveSerializer, responses={200: UserWordSerializer})
    def patch(self, request, pk: int):
        """Move a word to another list."""
        uw = get_object_or_404(UserWord, pk=pk, user=request.user)
        ser = MoveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        to = ser.validated_data["to"]
        if to == "learned":
            uw.box = leitner.MAX_BOX
            uw.seen = True
        elif to == "missed":
            uw.box = leitner.MIN_BOX
            uw.miss_count = max(uw.miss_count, 1)
            uw.seen = True
        uw.want_to_learn = to == "want" or (uw.want_to_learn and to != "learned")
        uw.save()
        return Response(UserWordSerializer(uw).data)

    @extend_schema(
        parameters=[OpenApiParameter("list", str, enum=["learned", "missed", "want"])], responses={204: None}
    )
    def delete(self, request, pk: int):
        """Remove a word from one list (or entirely when no list is given)."""
        uw = get_object_or_404(UserWord, pk=pk, user=request.user)
        which = request.query_params.get("list")
        if which == "want":
            uw.want_to_learn = False
        elif which in ("learned", "missed"):
            uw.box, uw.miss_count, uw.correct_count, uw.seen = 1, 0, 0, False
        else:
            uw.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        if not uw.want_to_learn and not uw.seen:
            uw.delete()
        else:
            uw.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
