from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.serializers import TokenPairSerializer, UserSerializer
from accounts.services import merge_users, record_ref_code, ref_code_from_param, tokens_for
from duels.services import code_from_param, record_referral
from tts.providers import any_configured

from .verify import (
    TelegramAuthError,
    parse_unsigned_init_data,
    verify_init_data,
    verify_login_widget,
)


class InitDataSerializer(serializers.Serializer):
    init_data = serializers.CharField(allow_blank=True)
    duel_code = serializers.CharField(required=False, allow_blank=True, max_length=16)
    ref_code = serializers.CharField(required=False, allow_blank=True, max_length=12)


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
def get_or_create_tg_user(tg: dict, duel_code: str = "", ref_code: str = "") -> User:
    """`duel_code` / `ref_code`: the duel link or share card a brand-new user came through (recorded once)."""
    tg_id = int(tg["id"])
    user = User.objects.filter(telegram_id=tg_id).first()
    if user is None:
        lang = tg.get("language_code", "")
        user = User.objects.create_user(
            telegram_id=tg_id,
            display_name=_display_name(tg),
            ui_language="ru" if lang == "ru" else ("en" if lang == "en" else "uz"),
        )
        if not record_referral(user, duel_code):
            record_ref_code(user, ref_code)
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
        # Signed start_param of t.me/<bot>/<app>?startapp=duel_<code>, or the duel page that was opened.
        start = payload.get("start_param")
        code = code_from_param(start) or ser.validated_data.get("duel_code", "")
        ref = ref_code_from_param(start) or (ser.validated_data.get("ref_code") or "").lower()
        return Response(tokens_for(get_or_create_tg_user(payload["user"], code, ref)))


class WidgetLoginView(APIView):
    """Website login via the Telegram Login Widget."""

    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=WidgetSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        ser = WidgetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            # not part of the signed payload
            fields = {k: v for k, v in request.data.items() if k not in ("duel_code", "ref_code")}
            payload = verify_any(widget=fields)
        except TelegramAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        code = str(request.data.get("duel_code") or "")[:16]
        ref = str(request.data.get("ref_code") or "")[:12].lower()
        return Response(tokens_for(get_or_create_tg_user(payload["user"], code, ref)))


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
                "app_short_name": settings.TELEGRAM_APP_SHORT_NAME,
                "telegram_mock": settings.TELEGRAM_MOCK,
                "ocr_mock": settings.OCR_MOCK,
                "ocr_daily_limit": settings.OCR_DAILY_LIMIT,
                "tts": any_configured(),
            }
        )
