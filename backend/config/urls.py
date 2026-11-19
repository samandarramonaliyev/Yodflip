from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(_request):
    return JsonResponse({"ok": True, "ocr_mock": settings.OCR_MOCK, "telegram_mock": settings.TELEGRAM_MOCK})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/auth/", include("accounts.urls")),
    path("api/auth/telegram/", include("telegram_auth.urls")),
    path("api/words/", include("words.urls")),
    path("api/", include("decks.urls")),
    path("api/games/", include("games.urls")),
    path("api/ocr/", include("ocr.urls")),
    path("api/gamification/", include("gamification.urls")),
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]
