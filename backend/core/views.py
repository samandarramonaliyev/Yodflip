from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_safe

from .models import StoredFile

# Telegram Web (web.telegram.org) shows Mini Apps inside an iframe.
FRAME_ANCESTORS = "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"


@require_safe
def health(_request):
    """Liveness + database check for the platform health check."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 - report, don't crash
        db_ok = False
    return JsonResponse(
        {"ok": db_ok, "db": db_ok, "ocr_mock": settings.OCR_MOCK, "telegram_mock": settings.TELEGRAM_MOCK},
        status=200 if db_ok else 503,
    )


@require_safe
@cache_control(public=True, max_age=31536000, immutable=True)
def media(_request, path: str):
    """Serve database-stored media (names are random UUIDs, so they can be cached forever)."""
    obj = StoredFile.objects.filter(name=path).only("content", "content_type").first()
    if obj is None:
        raise Http404
    resp = HttpResponse(bytes(obj.content), content_type=obj.content_type)
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@require_safe
@xframe_options_exempt
def spa(_request, path: str = ""):
    """Serve the React app's index.html for client-side routes."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse(
            "Frontend build not found. Run `npm run build` in frontend/ (or use the Vite dev server).",
            status=503,
            content_type="text/plain",
        )
    resp = FileResponse(open(index, "rb"), content_type="text/html; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    resp["Content-Security-Policy"] = FRAME_ANCESTORS
    return resp
