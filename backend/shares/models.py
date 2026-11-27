import uuid

from django.conf import settings
from django.db import models

TEMPLATES = [(t, t) for t in ("game", "level", "exam", "streak", "duel", "league", "weekly")]
PLATFORMS = [(p, p) for p in ("story", "telegram_link", "webshare", "download", "copy")]


def image_path(instance, filename) -> str:
    return f"shares/{uuid.uuid4().hex}.png"  # random, unguessable name (the URL is public)


class ShareEvent(models.Model):
    """One tap on a share button (for admin analytics)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    template = models.CharField(max_length=10, choices=TEMPLATES)
    platform = models.CharField(max_length=15, choices=PLATFORMS)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.template} → {self.platform}"


class ShareImage(models.Model):
    """A card PNG uploaded so Telegram can fetch it (stories, downloads). Deleted after 48 hours."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    file = models.FileField(upload_to=image_path)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
