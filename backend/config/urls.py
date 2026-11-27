from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core import views as core_views
from tts import views as tts_views
from words.views import MyWordsView

urlpatterns = [
    path("admin/tts-check/", tts_views.check, name="tts-check"),
    path("admin/tts-check/url/", tts_views.check_url, name="tts-check-url"),
    path("admin/broadcast/", include("broadcasts.urls")),
    path("admin/", admin.site.urls),
    path("api/health/", core_views.health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/auth/", include("accounts.urls")),
    path("api/auth/telegram/", include("telegram_auth.urls")),
    path("api/words/", include("words.urls")),
    path("api/levels/", include("words.level_urls")),
    path("api/me/words/", MyWordsView.as_view(), name="my-words"),
    path("api/", include("decks.urls")),
    path("api/games/", include("games.urls")),
    path("api/ocr/", include("ocr.urls")),
    path("api/duels/", include("duels.urls")),
    path("api/quiz/", include("botquiz.urls")),
    path("api/exams/", include("exams.urls")),
    path("api/tts/", include("tts.urls")),
    path("api/gamification/", include("gamification.urls")),
    path("api/classes/", include("classes.urls")),
    path("bot/", include("telegram_bot.urls")),  # Telegram webhook + reminder cron
    path(f"{settings.MEDIA_URL.strip('/')}/<path:path>", core_views.media, name="media"),
    # Everything else is a client-side route of the React app.
    re_path(r"^(?!api/|admin/|static/|media/|assets/|bot/)(?P<path>.*)$", core_views.spa, name="spa"),
]
