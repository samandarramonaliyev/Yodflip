from django.urls import path

from . import views

urlpatterns = [path("settings/", views.QuizSettingsView.as_view(), name="quiz-settings")]
