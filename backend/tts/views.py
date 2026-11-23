from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import TtsAudio
from .providers import RATES, get_provider
from .text import spoken_text

GERMAN = (
    "der Bahnhof, das Mädchen, die Straße, das Eichhörnchen, das Restaurant, die Psychologie, der Ingenieur, "
    "die Brötchen, der Schlüssel, die Übung, der Fußball, die Größe, das Streichholzschächtelchen, "
    "die Geschwindigkeitsbegrenzung, der Krankenwagen, die Waschmaschine, das Schwimmbad, der Kühlschrank, "
    "die Garage, der Chef, das Niveau, der Orangensaft, die Chance, das Museum, der Psychologe, die Familie, "
    "die Möglichkeit, der Zeuge, das Öl, fünfundzwanzig"
).replace("\u00ad", "")
ENGLISH = "through, schedule, comfortable, vegetable, thorough, Wednesday, colleague, entrepreneur, water, world"


class TtsView(APIView):
    """URL of the neural audio for a text. {"url": null, "fallback": true} → use the browser voice."""

    @extend_schema(
        parameters=[
            OpenApiParameter("text", str, required=True),
            OpenApiParameter("lang", str, enum=list(services.LANGS), required=True),
            OpenApiParameter("rate", str, enum=["normal", "slow"]),
            OpenApiParameter("voice", str, enum=["female", "male", "us", "uk"]),
        ],
        responses={200: dict},
    )
    def get(self, request):
        p = request.query_params
        lang, rate = p.get("lang", ""), p.get("rate") or "normal"
        raw = p.get("text") or ""
        if lang not in services.LANGS:
            raise ValidationError({"lang": "invalid_lang"})
        if rate not in RATES:
            raise ValidationError({"rate": "invalid_rate"})
        if len(raw) > services.MAX_CHARS:
            raise ValidationError({"text": "too_long"})
        text = spoken_text(raw, lang)
        if not any(c.isalnum() for c in text):
            raise ValidationError({"text": "empty"})
        try:
            url = services.get_url(request.user, text, lang, rate, p.get("voice") or "")
        except services.LimitReached:
            raise Throttled(detail="tts_daily_limit") from None
        return Response({"url": url, "fallback": url is None, "text": text, "lang": lang})


@require_safe
@cache_control(public=True, max_age=31536000, immutable=True)
def audio(_request, key: str):
    """Cached bytes. The sha256 key is the only identifier, so the URL can be cached forever."""
    row = TtsAudio.objects.filter(key=key).exclude(data=None).first()
    if row is None:
        raise Http404
    resp = HttpResponse(bytes(row.data), content_type="audio/mpeg")
    resp["Accept-Ranges"] = "none"
    return resp


@staff_member_required
def check(request):
    """/admin/tts-check/: compare voices."""
    provider = get_provider()
    rows = [("de", w.strip()) for w in GERMAN.split(",")] + [("en", w.strip()) for w in ENGLISH.split(",")]
    ctx = {
        "provider": provider.name,
        "configured": provider.configured(),
        "rows": [{"lang": lang, "text": text, "voices": provider.voices[lang]} for lang, text in rows],
    }
    return render(request, "tts/check.html", ctx)


@staff_member_required
def check_url(request):
    """JSON for the check page (admin session instead of JWT)."""
    from django.http import JsonResponse

    lang, rate = request.GET.get("lang"), request.GET.get("rate", "normal")
    text = spoken_text((request.GET.get("text") or "")[: services.MAX_CHARS], lang or "")
    if lang not in services.LANGS or rate not in RATES or not text:
        return JsonResponse({"detail": "invalid"}, status=400)
    try:
        url = services.get_url(request.user, text, lang, rate, request.GET.get("voice", ""))
    except services.LimitReached:
        return JsonResponse({"detail": "limit"}, status=429)
    return JsonResponse({"url": url})
