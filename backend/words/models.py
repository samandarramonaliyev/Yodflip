from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import CEFR_CHOICES, TRACK_CHOICES

ARTICLE_CHOICES = [("der", "der"), ("die", "die"), ("das", "das")]
TRANSLATION_LANGS = ("uz", "ru", "en", "de")
TRANSLATION_LANG_CHOICES = [("uz", "O'zbekcha"), ("ru", "Русский"), ("en", "English"), ("de", "Deutsch")]


def allowed_translation_langs(track: str) -> list[str]:
    """Translation languages for a learning track: never the track's own language."""
    return [lang for lang in TRANSLATION_LANGS if lang != track]


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
        # A word belongs to exactly one level inside its track.
        unique_together = ("track", "word", "article")
        ordering = ("track", "level", "pack__order", "id")

    def __str__(self):
        return self.display

    @property
    def display(self) -> str:
        return f"{self.article} {self.word}" if self.article else self.word


class WordTranslation(models.Model):
    """Translation of a built-in word into one language (uz / ru / en / de, never its own)."""

    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="translations")
    lang = models.CharField(max_length=2, choices=TRANSLATION_LANG_CHOICES)
    text = models.CharField(max_length=200)
    example_translation = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["word", "lang"], name="uniq_word_translation_lang")]

    def __str__(self):
        return f"{self.word} → {self.lang}: {self.text}"


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


class LevelRound(models.Model):
    """One round of a level game built by the server (the "session" of the level API).

    Stores which words were shown and which of them were review fillers, so answers can be
    validated server-side and the next rounds can avoid the words of the last sessions.
    """

    session_id = models.CharField(max_length=40, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="level_rounds")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES)
    game = models.CharField(max_length=30, blank=True)
    word_ids = models.JSONField(default=list)
    filler_ids = models.JSONField(default=list)
    xp_awarded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["user", "track", "-created_at"])]

    def __str__(self):
        return f"{self.user} · {self.track}/{self.level} · {self.session_id}"


class UserLevelWord(models.Model):
    """Level progress of one built-in word for one user. FOUND = LEARNED, permanently."""

    MAX_FILLER_USES = 2

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="level_words")
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="level_progress")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES)
    found_at = models.DateTimeField(null=True, blank=True)
    found_round = models.ForeignKey(LevelRound, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    filler_uses = models.PositiveSmallIntegerField(default=0)
    last_shown_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "word"], name="uniq_user_level_word"),
            models.CheckConstraint(condition=models.Q(filler_uses__lte=2), name="filler_uses_max_2"),
        ]
        indexes = [models.Index(fields=["user", "track", "level", "found_at"])]

    def __str__(self):
        return f"{self.user} · {self.word} · {'found' if self.found_at else 'open'}"


class LevelAnswer(models.Model):
    """First answer for a word inside one round; makes retries and double taps idempotent."""

    round = models.ForeignKey(LevelRound, on_delete=models.CASCADE, related_name="answers")
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="+")
    correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["round", "word"], name="uniq_round_word_answer")]


class LevelCompletion(models.Model):
    """A level finished at 100%. The unique row makes the completion bonus a one-time event."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="level_completions")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES)
    bonus_xp = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "track", "level"], name="uniq_level_completion")]


class FlashAnswer(models.Model):
    """One "Topdim / Topa olmadim" answer on a two-sided flashcard.

    `client_id` makes retries idempotent; `snapshot` holds the list state before the answer so
    "Bekor qilish" (undo) can restore it exactly.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="flash_answers")
    client_id = models.CharField(max_length=64)
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    known = models.BooleanField()
    userword = models.ForeignKey(UserWord, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    snapshot = models.JSONField(default=dict)
    level_word = models.ForeignKey(
        UserLevelWord, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )  # set when this answer found a level word for the first time
    card = models.ForeignKey("decks.Card", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    card_prev_status = models.CharField(max_length=10, blank=True)
    result = models.JSONField(default=dict)
    undone = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "client_id"], name="uniq_flash_client_id")]
