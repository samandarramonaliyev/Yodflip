from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from words import study
from words.level_views import STUDY_PARAMS, round_items
from words.serializers import WordSerializer
from words.translations import apply_translations, resolve

from . import services


class PackListView(APIView):
    @extend_schema(parameters=[OpenApiParameter("track", str, enum=["en", "de"])], responses={200: dict})
    def get(self, request):
        track = request.query_params.get("track") or request.user.active_track
        if track not in ("en", "de"):
            raise ValidationError({"track": "invalid_track"})
        return Response({"track": track, "packs": services.pack_list(request.user, track)})


class PackDetailView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request, slug: str):
        return Response(services.detail(request.user, services.get_pack(slug)))


class PackWordsView(APIView):
    @extend_schema(parameters=[OpenApiParameter("topic", str)], responses={200: WordSerializer(many=True)})
    def get(self, request, slug: str):
        pack = services.get_pack(slug)
        words = list(services.pack_words(pack, request.query_params.get("topic") or "").select_related("pack"))
        lang, _ = resolve(pack.track, request.query_params.get("translation_lang"))
        items = {i["word_id"]: i for i in apply_translations(_items(words), lang)}
        return Response(
            [
                {
                    **WordSerializer(w).data,
                    "translation": items[w.id]["translation"],
                    "example_tr": items[w.id]["example_tr"],
                }
                for w in words
            ]
        )


def _items(words):
    from games.sources import item_from_word

    return [item_from_word(w) for w in words]


class PackRoundView(APIView):
    """Same response as a level round; answers go to /api/levels/answer/."""

    @extend_schema(
        parameters=[
            OpenApiParameter("size", int),
            OpenApiParameter("game", str),
            OpenApiParameter("topic", str),
            OpenApiParameter("translation_lang", str, enum=["uz", "ru", "en", "de"]),
            OpenApiParameter("direction", str, enum=["forward", "reverse"]),
        ],
        responses={200: dict},
    )
    def get(self, request, slug: str):
        p = request.query_params
        pack = services.get_pack(slug)
        game = p.get("game") or ""
        if game == "derdiedas" and pack.track != "de":
            raise ValidationError({"detail": "game_not_available_for_track"})
        lang, direction = resolve(pack.track, p.get("translation_lang"), p.get("direction"))
        try:
            size = int(p.get("size", 6))
        except ValueError:
            size = 6
        rnd = services.build_round(request.user, pack, size, game=game, topic=p.get("topic") or "")
        return Response(
            {
                "session_id": rnd.session_id,
                "track": pack.track,
                "level": "",
                "completed": rnd.completed,
                "pool_done": rnd.pool_done,
                "translation_lang": lang,
                "direction": direction,
                "words": round_items(rnd.words, rnd.filler_ids, lang),
                "progress": services.progress_row(request.user, pack.track, pack.slug),
            }
        )


class GoalSerializer(serializers.Serializer):
    per_day = serializers.IntegerField(min_value=0, max_value=100)


class GoalView(APIView):
    """GET: my daily goal (or null)."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({"goal": services.goal_for(request.user)})


class PackGoalView(APIView):
    """POST {per_day}: "Bugun Goethe A1 dan 15 ta so'z"; 0 removes the goal."""

    @extend_schema(request=GoalSerializer, responses={200: dict})
    def post(self, request, slug: str):
        ser = GoalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        goal = services.set_goal(request.user, services.get_pack(slug), ser.validated_data["per_day"])
        return Response({"goal": goal})


class SimulationStartView(APIView):
    @extend_schema(request=dict, responses={201: dict})
    def post(self, request, slug: str):
        pack = services.get_pack(slug)
        sim = services.start_simulation(request.user, pack, str(request.data.get("translation_lang") or "uz"))
        return Response(services.simulation_payload(sim), status=status.HTTP_201_CREATED)


class SimAnswerSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0)
    choice = serializers.IntegerField(min_value=0, allow_null=True)


class SimulationAnswerView(APIView):
    """Answer the current question (choice null = skip); the next question comes back."""

    @extend_schema(request=SimAnswerSerializer, responses={200: dict})
    def post(self, request, pk: int):
        ser = SimAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(services.answer_question(request.user, pk, **ser.validated_data))


class SimViolationSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=services.VIOLATIONS)


class SimulationViolationView(APIView):
    @extend_schema(request=SimViolationSerializer, responses={200: dict})
    def post(self, request, pk: int):
        ser = SimViolationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(services.record_violation(request.user, pk, ser.validated_data["kind"]))


class SimulationSubmitView(APIView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request, pk: int):
        return Response(services.submit_simulation(request.user, pk))


class PackStudyView(APIView):
    """Word list study mode of a pack (lessons of 20). Reading never changes progress."""

    @extend_schema(parameters=STUDY_PARAMS, responses={200: dict})
    def get(self, request, slug: str):
        pack = services.get_pack(slug)
        topics = [(t.slug, t.emoji, services._names(t)) for t in pack.topics.all()]
        qs = services.pack_words(pack, request.query_params.get("topic") or "")
        links = dict(pack.pack_words.values_list("word_id", "topic__slug"))
        return Response(study.study_page(request, pack.track, qs, topics, lambda w: links.get(w.id, "")))
