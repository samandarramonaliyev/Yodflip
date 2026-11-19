from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.serializers import TokenPairSerializer, UserSerializer
from accounts.services import merge_users, tokens_for

from .verify import (
    TelegramAuthError,
    parse_unsigned_init_data,
    verify_init_data,
    verify_login_widget,
)


class InitDataSerializer(serializers.Serializer):
    init_data = serializers.CharField(allow_blank=True)


class WidgetSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    username = serializers.CharField(required=False, allow_blank=True)
    photo_url = serializers.CharField(required=False, allow_blank=True)
    auth_date = serializers.IntegerField()
    hash = serializers.CharField()


class LinkSerializer(serializers.Serializer):
    init_data = serializers.CharField(required=False, allow_blank=True)
    widget = serializers.DictField(required=False)


def verify_any(init_data: str | None = None, widget: dict | None = None) -> dict:
    token = settings.TELEGRAM_BOT_TOKEN
    max_age = settings.TELEGRAM_AUTH_MAX_AGE
    if init_data is not None:
        if not token:
            if settings.TELEGRAM_MOCK:
                return parse_unsigned_init_data(init_data)
            raise TelegramAuthError("telegram_not_configured")
        return verify_init_data(init_data, token, max_age=max_age)
    if widget is not None:
        if not token:
            if settings.TELEGRAM_MOCK:
                return {"user": widget}
            raise TelegramAuthError("telegram_not_configured")
        return verify_login_widget(widget, token, max_age=max_age)
    raise TelegramAuthError("no_payload")


def _display_name(tg: dict) -> str:
    name = " ".join(p for p in (tg.get("first_name"), tg.get("last_name")) if p).strip()
    return name or tg.get("username") or f"user{tg['id']}"


@transaction.atomic
def get_or_create_tg_user(tg: dict) -> User:
    tg_id = int(tg["id"])
    user = User.objects.filter(telegram_id=tg_id).first()
    if user is None:
        lang = tg.get("language_code", "")
        user = User.objects.create_user(
            telegram_id=tg_id,
            display_name=_display_name(tg),
            ui_language="ru" if lang == "ru" else ("en" if lang == "en" else "uz"),
        )
    user.telegram_username = tg.get("username") or user.telegram_username
    if tg.get("photo_url"):
        user.avatar_url = tg["photo_url"]
    user.save()
    return user


class WebAppLoginView(APIView):
    """Mini App automatic login with Telegram initData (HMAC-SHA256 verified)."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=InitDataSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        ser = InitDataSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payload = verify_any(init_data=ser.validated_data["init_data"])
        except TelegramAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        if "user" not in payload:
            return Response({"detail": "no_user"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(tokens_for(get_or_create_tg_user(payload["user"])))


class WidgetLoginView(APIView):
    """Website login via the Telegram Login Widget."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=WidgetSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        ser = WidgetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payload = verify_any(widget=dict(request.data))
        except TelegramAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(tokens_for(get_or_create_tg_user(payload["user"])))


class LinkTelegramView(APIView):
    """Link a Telegram identity to the logged-in (web) account; merges a TG-only account."""

    @extend_schema(request=LinkSerializer, responses={200: UserSerializer})
    def post(self, request):
        ser = LinkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            payload = verify_any(
                init_data=ser.validated_data.get("init_data"),
                widget=ser.validated_data.get("widget"),
            )
        except TelegramAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        tg = payload.get("user") or {}
        tg_id = int(tg.get("id", 0))
        me: User = request.user
        if me.telegram_id and me.telegram_id != tg_id:
            return Response({"detail": "already_linked"}, status=status.HTTP_409_CONFLICT)
        other = User.objects.filter(telegram_id=tg_id).exclude(pk=me.pk).first()
        if other:
            if other.email:
                return Response({"detail": "telegram_in_use"}, status=status.HTTP_409_CONFLICT)
            me = merge_users(me, other)
        me.telegram_id = tg_id
        me.telegram_username = tg.get("username", "") or me.telegram_username
        me.avatar_url = me.avatar_url or tg.get("photo_url", "")
        me.save()
        return Response(UserSerializer(me).data)


class PublicConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(
            {
                "bot_username": settings.TELEGRAM_BOT_USERNAME,
                "telegram_mock": settings.TELEGRAM_MOCK,
                "ocr_mock": settings.OCR_MOCK,
                "ocr_daily_limit": settings.OCR_DAILY_LIMIT,
            }
        )
