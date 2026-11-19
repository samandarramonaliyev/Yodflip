from django.conf import settings
from django.db import models

from accounts.models import TRACK_CHOICES


class DailyChallengeScore(models.Model):
    """First attempt of a user at the Daily Challenge of one track on one day."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_scores")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    date = models.DateField()
    correct = models.PositiveSmallIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    score = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "track", "date")
        ordering = ("-score", "duration_ms")
