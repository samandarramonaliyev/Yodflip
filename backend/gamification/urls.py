from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.ProfileStatsView.as_view(), name="profile-stats"),
    path("achievements/", views.AchievementsView.as_view(), name="achievements"),
    path("leaderboard/", views.LeaderboardView.as_view(), name="leaderboard"),
]
