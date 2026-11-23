from django.urls import path

from . import views

urlpatterns = [
    path("", views.PackListView.as_view(), name="exam-packs"),
    path("goal/", views.GoalView.as_view(), name="exam-goal"),
    path("simulations/<int:pk>/submit/", views.SimulationSubmitView.as_view(), name="exam-sim-submit"),
    path("<slug:slug>/", views.PackDetailView.as_view(), name="exam-pack"),
    path("<slug:slug>/words/", views.PackWordsView.as_view(), name="exam-words"),
    path("<slug:slug>/round/", views.PackRoundView.as_view(), name="exam-round"),
    path("<slug:slug>/goal/", views.PackGoalView.as_view(), name="exam-set-goal"),
    path("<slug:slug>/simulation/", views.SimulationStartView.as_view(), name="exam-sim-start"),
]
