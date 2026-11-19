from datetime import datetime, time

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from gamification.services import award_event

from .models import ScanLog
from .schema import ExtractionError
from .services import extract_pairs

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/gif"}


def scans_today(user) -> int:
    start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    return ScanLog.objects.filter(user=user, created_at__gte=start).count()


class ScanView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "format": "binary"},
                    "track": {"type": "string", "enum": ["en", "de"]},
                },
            }
        },
        responses={200: dict},
    )
    def post(self, request):
        used = scans_today(request.user)
        if used >= settings.OCR_DAILY_LIMIT:
            return Response(
                {"detail": "scan_limit_reached", "limit": settings.OCR_DAILY_LIMIT},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        f = request.FILES.get("image")
        if not f:
            return Response({"detail": "image_required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if f.size > settings.MAX_UPLOAD_BYTES:
                return Response(
                    {"detail": "image_too_large", "max_mb": 10}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                )
            if f.content_type and f.content_type not in ALLOWED_TYPES:
                return Response({"detail": "unsupported_type"}, status=status.HTTP_400_BAD_REQUEST)
            raw = f.read()
        finally:
            # Uploaded images are never persisted; close (and so delete) any temp file now.
            f.close()
        track = request.data.get("track") or request.user.active_track
        try:
            result = extract_pairs(raw, track_hint=track)
        except ExtractionError as exc:
            ScanLog.objects.create(user=request.user, ok=False)
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        finally:
            del raw
        ScanLog.objects.create(user=request.user, engine=result["engine"], pairs_found=len(result["pairs"]))
        new = award_event(request.user, "scan")
        result["new_achievements"] = new
        result["scans_left"] = max(0, settings.OCR_DAILY_LIMIT - used - 1)
        result["track_mismatch"] = result["language"] != track
        return Response(result)


class ScanQuotaView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        used = scans_today(request.user)
        return Response(
            {
                "used": used,
                "limit": settings.OCR_DAILY_LIMIT,
                "left": max(0, settings.OCR_DAILY_LIMIT - used),
                "mock": settings.OCR_MOCK,
            }
        )
