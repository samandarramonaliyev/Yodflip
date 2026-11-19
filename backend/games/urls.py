from django.urls import path

from . import bot_views, views

urlpatterns = [
    path("words/", views.WordsView.as_view(), name="game-words"),
    path("results/", views.ResultsView.as_view(), name="game-results"),
    path("daily/leaderboard/", views.DailyLeaderboardView.as_view(), name="daily-leaderboard"),
    path("bot/stats/<int:tg_id>/", bot_views.BotStatsView.as_view(), name="bot-stats"),
    path("bot/daily/", bot_views.BotDailyView.as_view(), name="bot-daily"),
    path("bot/reminder/<int:tg_id>/", bot_views.BotReminderSetView.as_view(), name="bot-reminder"),
    path("bot/reminders-due/", bot_views.BotRemindersDueView.as_view(), name="bot-reminders-due"),
]
