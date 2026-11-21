from django.conf import settings
from django.db import models

from accounts.models import TRACK_CHOICES


class DailyActivity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity")
    date = models.DateField()
    xp = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    games = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("user", "date")
        ordering = ("-date",)


class GameSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    game = models.CharField(max_length=30)
    mode = models.CharField(max_length=20, default="memorize")
    source = models.CharField(max_length=40, blank=True)
    translation_lang = models.CharField(max_length=2, blank=True)  # memorization games only
    xp = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class UserAchievement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="achievements")
    code = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "code")
