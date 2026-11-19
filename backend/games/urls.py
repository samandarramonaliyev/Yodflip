from django.urls import path

from . import views

urlpatterns = [
    path("words/", views.WordsView.as_view(), name="game-words"),
    path("results/", views.ResultsView.as_view(), name="game-results"),
    path("daily/leaderboard/", views.DailyLeaderboardView.as_view(), name="daily-leaderboard"),
]
