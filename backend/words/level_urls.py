from django.urls import path

from . import level_views as v

urlpatterns = [
    path("answer/", v.AnswerView.as_view(), name="level-answer"),
    path("<str:track>/", v.TrackProgressView.as_view(), name="level-progress"),
    path("<str:track>/<str:level>/", v.LevelDetailView.as_view(), name="level-detail"),
    path("<str:track>/<str:level>/words/", v.LevelStudyView.as_view(), name="level-study"),
    path("<str:track>/<str:level>/round/", v.RoundView.as_view(), name="level-round"),
]
