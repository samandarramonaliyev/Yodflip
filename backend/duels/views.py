from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import TRACK_CHOICES

from . import services
from .models import Duel, DuelParticipant
from .questions import public_questions


def current_user(request):
    return request.user if request.user.is_authenticated else None


def guest_token(request) -> str:
    return (request.headers.get("X-Duel-Guest") or "")[:64]


def side(p: DuelParticipant | None, duel: Duel, reveal: bool) -> dict | None:
    if p is None:
        return None
    out = {**services.player(p), "finished": bool(p.finished_at), "role": p.role}
    if reveal and p.finished_at:
        n = len(duel.words)
        out.update(score=p.score, time_ms=p.time_ms, accuracy=round(100 * p.score / n) if n else 0)
    return out


def payload(duel: Duel, me: DuelParticipant | None) -> dict:
    parts = {p.role: p for p in duel.participants.select_related("user")}
    creator, opp = parts.get(DuelParticipant.CREATOR), parts.get(DuelParticipant.OPPONENT)
    data = {
        "code": duel.code,
        "track": duel.track,
        "mode": duel.mode,
        "source": duel.source,
        "source_ref": duel.source_ref,
        "source_label": duel.source_label,
        "translation_lang": duel.translation_lang,
        "status": duel.status,
        "total": len(duel.words),
        "expires_at": duel.expires_at,
        "web_link": services.web_link(duel.code),
        "telegram_link": services.telegram_link(duel.code),
        "challenger": {"name": duel.creator.display_name, "avatar_url": duel.creator.avatar_url},
        # The challenger's score is part of the invitation; answers are never shown.
        "creator": side(creator, duel, True),
        "opponent": side(opp, duel, duel.status == Duel.COMPLETED),
        "is_draw": duel.is_draw,
        "me": None,
    }
    if me:
        data["me"] = {
            "role": me.role,
            "finished": bool(me.finished_at),
            "is_guest": me.user_id is None,
            "answered": [a["index"] for a in me.answers],
            "score": me.score,
            "time_ms": me.time_ms,
        }
        other = opp if me.role == DuelParticipant.CREATOR else creator
        if duel.status == Duel.COMPLETED and other:
            data["outcome"] = services.outcome_of(me, other)
            data["xp"] = services.XP[data["outcome"]]
        if me.finished_at:
            right = {a["index"] for a in me.answers if a["correct"]}
            data["review"] = [
                {"term": q["prompt"], "answer": q["options"][q["answer"]], "correct": n in right}
                for n, q in enumerate(duel.words)
            ]
    return data


class DuelCreateSerializer(serializers.Serializer):
    track = serializers.ChoiceField(choices=TRACK_CHOICES)
    source = serializers.ChoiceField(choices=["level", "exam", "deck"])
    source_ref = serializers.CharField(max_length=60)
    mode = serializers.ChoiceField(choices=["speed", "match"])
    translation_lang = serializers.ChoiceField(choices=["uz", "ru", "en", "de"], required=False, default="uz")


class DuelListView(APIView):
    """GET: my duels + stats. POST: create a duel (the creator plays first)."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(services.stats(request.user))

    @extend_schema(request=DuelCreateSerializer, responses={201: dict})
    def post(self, request):
        ser = DuelCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        duel = services.create(
            request.user,
            track=d["track"],
            source=d["source"],
            ref=d["source_ref"],
            mode=d["mode"],
            lang=d["translation_lang"],
        )
        return Response(payload(duel, None), status=status.HTTP_201_CREATED)


class PublicDuelView(APIView):
    """Guests may play: identified by the X-Duel-Guest token that /start/ returned."""

    permission_classes = [permissions.AllowAny]

    def load(self, request, code):
        return services.get(code), current_user(request), guest_token(request)


class DuelDetailView(PublicDuelView):
    @extend_schema(responses={200: dict})
    def get(self, request, code: str):
        duel, user, token = self.load(request, code)
        return Response(payload(duel, services.participant_for(duel, user, token)))


class DuelStartView(PublicDuelView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request, code: str):
        duel, user, token = self.load(request, code)
        p = services.start(duel, user, token)
        data = payload(duel, p)
        if not p.finished_at:
            data["questions"] = public_questions(duel)
        if p.user_id is None:
            data["guest_token"] = p.guest_token
        return Response(data)


class DuelAnswerSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0)
    choice = serializers.IntegerField(min_value=0)
    client_ms = serializers.IntegerField(required=False, allow_null=True)  # how long the player thought


class DuelAnswerView(PublicDuelView):
    @extend_schema(request=DuelAnswerSerializer, responses={200: dict})
    def post(self, request, code: str):
        duel, user, token = self.load(request, code)
        ser = DuelAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        return Response(
            services.answer(duel, user, token, index=d["index"], choice=d["choice"], client_ms=d.get("client_ms"))
        )


class DuelFinishView(PublicDuelView):
    @extend_schema(request=None, responses={200: dict})
    def post(self, request, code: str):
        duel, user, token = self.load(request, code)
        p = services.finish(duel, user, token)
        duel.refresh_from_db()
        return Response(payload(duel, p))


class DuelClaimView(APIView):
    """After a guest signs in: save the guest result to the account."""

    @extend_schema(request=None, responses={200: dict})
    def post(self, request, code: str):
        token = guest_token(request)
        if not token:
            raise ValidationError({"detail": "guest_token_required"})
        duel = services.get(code)
        p = services.claim(duel, request.user, token)
        duel.refresh_from_db()
        return Response(payload(duel, p))


class DuelRematchView(APIView):
    @extend_schema(request=None, responses={201: dict})
    def post(self, request, code: str):
        duel = services.rematch(services.get(code), request.user)
        return Response(payload(duel, services.participant_for(duel, request.user)), status=status.HTTP_201_CREATED)
