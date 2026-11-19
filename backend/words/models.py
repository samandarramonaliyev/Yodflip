from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import CEFR_CHOICES, TRACK_CHOICES

ARTICLE_CHOICES = [("der", "der"), ("die", "die"), ("das", "das")]


def term_key(term: str) -> str:
    """Normalised identity of a term inside a track (case/space-insensitive)."""
    return " ".join((term or "").strip().lower().split())


class Pack(models.Model):
    """A themed pack of built-in words inside one level of one track (e.g. EN · A1 · Food)."""

    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES)
    slug = models.SlugField(max_length=60)
    name_uz = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    name_ru = models.CharField(max_length=80)
    emoji = models.CharField(max_length=8, default="📚")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("track", "level", "slug")
        ordering = ("track", "level", "order")

    def __str__(self):
        return f"{self.track.upper()} {self.level} · {self.name_en}"


class Word(models.Model):
    """A built-in word. Stores BOTH a same-language definition and an Uzbek translation."""

    track = models.CharField(max_length=2, choices=TRACK_CHOICES, db_index=True)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES, db_index=True)
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name="words")
    word = models.CharField(max_length=120)  # German nouns stored without article
    article = models.CharField(max_length=3, choices=ARTICLE_CHOICES, blank=True)
    part_of_speech = models.CharField(max_length=20)
    definition = models.CharField(max_length=300)  # same language as the word
    translation_uz = models.CharField(max_length=200)  # Uzbek, Latin script
    example = models.CharField(max_length=300, blank=True)
    example_uz = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = ("track", "level", "word", "article")
        ordering = ("track", "level", "pack__order", "id")

    def __str__(self):
        return self.display

    @property
    def display(self) -> str:
        return f"{self.article} {self.word}" if self.article else self.word


class UserWord(models.Model):
    """Per-user, per-track progress of one term (Leitner box) + the three profile lists.

    Terms from built-in words, decks and scanned sets all share this table, keyed by the
    normalised term, so the Learned / Missed / Want-to-learn lists are unified.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="words")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    term_key = models.CharField(max_length=200)
    term = models.CharField(max_length=200)
    article = models.CharField(max_length=3, blank=True)
    translation_uz = models.CharField(max_length=300, blank=True)
    definition = models.CharField(max_length=500, blank=True)
    word = models.ForeignKey(Word, null=True, blank=True, on_delete=models.SET_NULL)

    box = models.PositiveSmallIntegerField(default=1)
    correct_count = models.PositiveIntegerField(default=0)
    miss_count = models.PositiveIntegerField(default=0)
    seen = models.BooleanField(default=False)
    want_to_learn = models.BooleanField(default=False)
    due_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "track", "term_key")
        indexes = [models.Index(fields=["user", "track", "box"]), models.Index(fields=["user", "track", "due_at"])]

    def __str__(self):
        return f"{self.user} · {self.term} (box {self.box})"

    @property
    def is_learned(self) -> bool:
        return self.box >= 5

    @property
    def is_missed(self) -> bool:
        return self.box == 1 and self.miss_count > 0
