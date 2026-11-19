from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("decks", views.DeckViewSet, basename="deck")
router.register("sets", views.WordSetViewSet, basename="wordset")

urlpatterns = [
    path("decks/quick-add/", views.QuickAddCardView.as_view(), name="deck-quick-add"),
    path("decks/public/", views.PublicDecksView.as_view(), name="deck-public"),
    path("decks/shared/<str:code>/", views.SharedDeckView.as_view(), name="deck-shared"),
] + router.urls
