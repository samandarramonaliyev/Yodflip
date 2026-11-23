import secrets
import string

from django.conf import settings
from django.db import models

from accounts.models import TRACK_CHOICES

ALPHABET = string.ascii_letters + string.digits  # safe inside Telegram's startapp parameter


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


def new_guest_token() -> str:
    return secrets.token_urlsafe(24)


class Duel(models.Model):
    """Two players, the same frozen words. `words` holds the questions AND the answers (server only)."""

    PENDING, OPEN, COMPLETED, EXPIRED = "pending", "open", "completed", "expired"
    STATUSES = [("pending", "Pending"), ("open", "Open"), ("completed", "Completed"), ("expired", "Expired")]
    MODES = [("speed", "Speed Match"), ("match", "Match Game")]
    SOURCES = [("level", "Level"), ("exam", "Exam pack"), ("deck", "Deck")]

    code = models.CharField(max_length=16, unique=True, default=new_code)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="duels_created")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    source = models.CharField(max_length=10, choices=SOURCES)
    source_ref = models.CharField(max_length=60)  # level code, exam pack slug or deck id
    source_label = models.CharField(max_length=120, blank=True)
    mode = models.CharField(max_length=10, choices=MODES)
    translation_lang = models.CharField(max_length=2, default="uz")
    words = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="duels_won"
    )
    is_draw = models.BooleanField(default=False)
    rematch_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="rematches")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self):
        return f"{self.code} ({self.track}/{self.mode}, {self.status})"


class DuelParticipant(models.Model):
    """One player. Guests have no user until they claim the result with `guest_token`."""

    CREATOR, OPPONENT = "creator", "opponent"
    ROLES = [("creator", "Creator"), ("opponent", "Opponent")]

    duel = models.ForeignKey(Duel, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="duel_entries"
    )
    role = models.CharField(max_length=10, choices=ROLES)
    guest_token = models.CharField(max_length=64, default=new_guest_token)
    score = models.PositiveSmallIntegerField(default=0)
    time_ms = models.PositiveIntegerField(default=0)
    answers = models.JSONField(default=list, blank=True)  # [{index, choice, correct, ms}]
    started_at = models.DateTimeField()
    last_answer_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    rewarded = models.BooleanField(default=False)  # duel XP given (exactly once)

    class Meta:
        constraints = [
            # One creator and one opponent per duel code, enforced by the database.
            models.UniqueConstraint(fields=["duel", "role"], name="uniq_duel_role"),
            models.UniqueConstraint(fields=["duel", "user"], name="uniq_duel_user"),
        ]

    def __str__(self):
        return f"{self.duel.code} · {self.role} · {self.user or 'guest'}"
