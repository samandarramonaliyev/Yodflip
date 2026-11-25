from django.urls import path, re_path

from . import views

urlpatterns = [
    path("webhook/<str:secret>/", views.webhook, name="bot-webhook"),
    # .../status/ and .../quiz/ must come before the catch-all route.
    re_path(r"^cron/(?P<secret>.+?)/status/?$", views.cron_status, name="bot-cron-status"),
    re_path(r"^cron/(?P<secret>.+?)/quiz/?$", views.cron, name="bot-cron-quiz"),
    # Secret may contain "/" or "+" (e.g. Render-generated base64); trailing slash optional,
    # so a cron service that drops it (or can't follow a redirect for POST) still works.
    re_path(r"^cron/(?P<secret>.+?)/?$", views.cron, name="bot-cron"),
]
