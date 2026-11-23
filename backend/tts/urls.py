from django.urls import path

from . import views

urlpatterns = [
    path("", views.TtsView.as_view(), name="tts"),
    path("audio/<str:key>.mp3", views.audio, name="tts-audio"),
]
