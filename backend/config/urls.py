from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core import views as core_views
from words.views import MyWordsView

urlpatterns = [
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
    path("api/gamification/", include("gamification.urls")),
    path("bot/", include("telegram_bot.urls")),  # Telegram webhook + reminder cron
    path(f"{settings.MEDIA_URL.strip('/')}/<path:path>", core_views.media, name="media"),
    # Everything else is a client-side route of the React app.
    re_path(r"^(?!api/|admin/|static/|media/|assets/|bot/)(?P<path>.*)$", core_views.spa, name="spa"),
]
