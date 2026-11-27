from django.urls import path

from . import views

urlpatterns = [
    path("", views.LeagueView.as_view(), name="league"),
    path("history/", views.LeagueHistoryView.as_view(), name="league-history"),
]
