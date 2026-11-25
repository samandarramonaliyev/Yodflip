from django.urls import path

from . import views

urlpatterns = [
    path("", views.page, name="broadcast"),
    path("count/", views.count, name="broadcast-count"),
    path("history/", views.history, name="broadcast-history"),
    path("submit/", views.submit, name="broadcast-submit"),
    path("<int:pk>/<str:action>/", views.act, name="broadcast-act"),
]
