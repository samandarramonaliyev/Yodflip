import io
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import PLATFORMS, TEMPLATES, ShareEvent, ShareImage
from .render import SIZES, render_card

MAX_UPLOAD = 4 * 1024 * 1024
KEEP = timedelta(hours=48)
UPLOADS_PER_DAY = 50


class EventSerializer(serializers.Serializer):
    template = serializers.ChoiceField(choices=TEMPLATES)
    platform = serializers.ChoiceField(choices=PLATFORMS)


class ShareEventView(APIView):
    """Log one share (template + platform) for the admin analytics."""

    @extend_schema(request=EventSerializer, responses={201: dict})
    def post(self, request):
        ser = EventSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ShareEvent.objects.create(user=request.user, **ser.validated_data)
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


def public_url(path: str) -> str:
    base = settings.PUBLIC_URL.rstrip("/")
    return f"{base}{path}" if base else path


class UploadView(APIView):
    """A finished card PNG → public URL (Telegram stories and downloads need a URL, not a blob)."""

    @extend_schema(request=None, responses={201: dict})
    def post(self, request):
        f = request.FILES.get("image")
        if f is None:
            return Response({"detail": "no_image"}, status=status.HTTP_400_BAD_REQUEST)
        if f.size > MAX_UPLOAD:
            return Response({"detail": "too_large"}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        since = timezone.now() - timedelta(days=1)
        if ShareImage.objects.filter(user=request.user, created_at__gte=since).count() >= UPLOADS_PER_DAY:
            return Response({"detail": "limit"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        data = f.read()
        try:
            with Image.open(io.BytesIO(data)) as im:
                fmt, size = im.format, im.size
                im.verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            return Response({"detail": "not_png"}, status=status.HTTP_400_BAD_REQUEST)
        if fmt != "PNG" or size not in SIZES.values():
            return Response({"detail": "bad_size"}, status=status.HTTP_400_BAD_REQUEST)
        from django.core.files.base import ContentFile

        content = ContentFile(data, name="card.png")
        content.content_type = "image/png"
        img = ShareImage.objects.create(user=request.user, file=content)
        return Response({"url": public_url(img.file.url)}, status=status.HTTP_201_CREATED)


class CardSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=list(SIZES), default="story")
    theme = serializers.ChoiceField(choices=["violet", "yellow", "dark"], default="violet")
    lang = serializers.CharField(max_length=2, required=False, allow_blank=True)
    content = serializers.DictField()
    name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    footer = serializers.CharField(max_length=120, required=False, allow_blank=True)
    link = serializers.CharField(max_length=300, required=False, allow_blank=True)


class RenderView(APIView):
    """Pillow fallback: draws the card on the server when the browser could not export it."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "share_render"

    @extend_schema(request=CardSerializer, responses={200: bytes})
    def post(self, request):
        ser = CardSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        png = render_card(ser.validated_data)
        resp = HttpResponse(png, content_type="image/png")
        resp["Cache-Control"] = "no-store"
        return resp


def cleanup(now=None) -> dict:
    """Cron part: uploaded card images are only needed for a moment (Telegram fetches them once)."""
    old = ShareImage.objects.filter(created_at__lt=(now or timezone.now()) - KEEP)
    n = 0
    for img in old.iterator():
        img.file.delete(save=False)
        img.delete()
        n += 1
    return {"due": n, "sent": 0}
