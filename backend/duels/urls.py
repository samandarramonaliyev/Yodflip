from django.urls import path

from . import views

urlpatterns = [
    path("", views.DuelListView.as_view(), name="duels"),
    path("<str:code>/", views.DuelDetailView.as_view(), name="duel-detail"),
    path("<str:code>/start/", views.DuelStartView.as_view(), name="duel-start"),
    path("<str:code>/answer/", views.DuelAnswerView.as_view(), name="duel-answer"),
    path("<str:code>/finish/", views.DuelFinishView.as_view(), name="duel-finish"),
    path("<str:code>/claim/", views.DuelClaimView.as_view(), name="duel-claim"),
    path("<str:code>/rematch/", views.DuelRematchView.as_view(), name="duel-rematch"),
]
