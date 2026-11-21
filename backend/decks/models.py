import secrets

from django.conf import settings
from django.db import models

from accounts.models import TRACK_CHOICES


def new_share_code() -> str:
    return secrets.token_urlsafe(8)


class Deck(models.Model):
    """Quizlet-style flashcard deck (term ↔ Uzbek translation)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="decks")
    name = models.CharField(max_length=120)
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    description = models.CharField(max_length=500, blank=True)
    # Language of the cards' "translation" side (uz / ru / en / de, never the track itself).
    translation_lang = models.CharField(max_length=2, default="uz")
    is_public = models.BooleanField(default=False)
    share_code = models.CharField(max_length=20, unique=True, default=new_share_code)
    copied_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return self.name


class Card(models.Model):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="cards")
    term = models.CharField(max_length=200)
    translation = models.CharField(max_length=300)  # in deck.translation_lang
    extra_translations = models.JSONField(default=dict, blank=True)  # {lang: text}, optional / AI-cached
    definition = models.CharField(max_length=500, blank=True)
    example = models.CharField(max_length=500, blank=True)
    article = models.CharField(max_length=3, blank=True)
    image = models.ImageField(upload_to="cards/", null=True, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.term} — {self.translation}"


class WordSet(models.Model):
    """Pairs extracted from a scanned book page (or typed by hand)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="word_sets")
    name = models.CharField(max_length=120)
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class SetPair(models.Model):
    word_set = models.ForeignKey(WordSet, on_delete=models.CASCADE, related_name="pairs")
    word = models.CharField(max_length=200)
    definition = models.CharField(max_length=500)  # same language as the word
    part_of_speech = models.CharField(max_length=30, blank=True)
    article = models.CharField(max_length=3, blank=True)
    translation_uz = models.CharField(max_length=300, blank=True)
    translations = models.JSONField(default=dict, blank=True)  # {"ru": ..., "en"/"de": ...}
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.word
