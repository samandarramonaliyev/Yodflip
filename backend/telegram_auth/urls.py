from django.urls import path

from . import views

urlpatterns = [
    path("webapp/", views.WebAppLoginView.as_view(), name="tg-webapp"),
    path("widget/", views.WidgetLoginView.as_view(), name="tg-widget"),
    path("link/", views.LinkTelegramView.as_view(), name="tg-link"),
    path("config/", views.PublicConfigView.as_view(), name="public-config"),
]
