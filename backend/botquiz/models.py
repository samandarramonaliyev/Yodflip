import secrets

from django.conf import settings
from django.db import models

from accounts.models import TRACK_CHOICES

DEFAULT_TZ = "Asia/Tashkent"
QUESTION_CHOICES = (5, 8, 10)


def new_sid() -> str:
    return secrets.token_hex(5)  # callback data stays far below Telegram's 64 bytes


class QuizSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_settings")
    enabled = models.BooleanField(default=True)
    hour = models.PositiveSmallIntegerField(default=19)  # 0-23 in the user's timezone
    timezone = models.CharField(max_length=50, default=DEFAULT_TZ)
    questions = models.PositiveSmallIntegerField(default=8)
    translation_lang = models.CharField(max_length=2, blank=True)  # blank = the language chosen in the app
    quiet_days = models.JSONField(default=list, blank=True)  # weekdays without a quiz, Monday = 0
    last_sent_on = models.DateField(null=True, blank=True)  # user's local date: at most one quiz per day
    last_sent_at = models.DateTimeField(null=True, blank=True)
    bot_blocked = models.BooleanField(default=False)  # Telegram answered 403

    class Meta:
        verbose_name_plural = "quiz settings"

    def __str__(self):
        return f"{self.user} · {self.hour}:00 {self.timezone}"


class QuizSession(models.Model):
    """One in-chat quiz. The questions live here; buttons only carry the session id and an index."""

    NEW, ACTIVE, DONE = "new", "active", "done"
    STATUSES = [("new", "New"), ("active", "Active"), ("done", "Done")]

    sid = models.CharField(max_length=16, unique=True, default=new_sid)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_sessions")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    translation_lang = models.CharField(max_length=2, default="uz")
    questions = models.JSONField(default=list)
    index = models.PositiveSmallIntegerField(default=0)
    correct = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=6, choices=STATUSES, default=NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.sid} · {self.user} ({self.status})"
