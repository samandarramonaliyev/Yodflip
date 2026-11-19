from django.urls import path

from . import views

urlpatterns = [
    path("webhook/<str:secret>/", views.webhook, name="bot-webhook"),
    path("cron/<str:secret>/", views.cron, name="bot-cron"),
]
