from django.conf import settings
from django.db import models

from accounts.models import TRACK_CHOICES
from words.models import Word


class ExamPack(models.Model):
    """Unofficial exam preparation pack: original lists, linked to the shared Word records."""

    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    slug = models.SlugField(max_length=60, unique=True)
    emoji = models.CharField(max_length=8, default="📘")
    name_uz = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    name_ru = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order",)

    def __str__(self):
        return self.slug


class ExamTopic(models.Model):
    pack = models.ForeignKey(ExamPack, on_delete=models.CASCADE, related_name="topics")
    slug = models.SlugField(max_length=60)
    emoji = models.CharField(max_length=8, default="📚")
    name_uz = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    name_ru = models.CharField(max_length=80)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order",)
        constraints = [models.UniqueConstraint(fields=["pack", "slug"], name="uniq_exam_topic")]

    def __str__(self):
        return f"{self.pack} / {self.slug}"


class PackWord(models.Model):
    pack = models.ForeignKey(ExamPack, on_delete=models.CASCADE, related_name="pack_words")
    word = models.ForeignKey(Word, on_delete=models.CASCADE, related_name="exam_links")
    topic = models.ForeignKey(ExamTopic, on_delete=models.CASCADE, related_name="pack_words")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("order",)
        constraints = [models.UniqueConstraint(fields=["pack", "word"], name="uniq_pack_word")]

    def __str__(self):
        return f"{self.pack} · {self.word}"


class ExamSimulation(models.Model):
    """30 frozen questions of one attempt (answers stay on the server until it is submitted)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_simulations")
    pack = models.ForeignKey(ExamPack, on_delete=models.CASCADE, related_name="simulations")
    translation_lang = models.CharField(max_length=2, default="uz")
    questions = models.JSONField(default=list)
    time_limit = models.PositiveIntegerField(default=600)  # seconds
    position = models.PositiveSmallIntegerField(default=0)  # questions are served one at a time
    answers = models.JSONField(default=dict, blank=True)  # {"0": 2}
    violations = models.JSONField(default=list, blank=True)  # [{kind, at}]
    terminated = models.BooleanField(default=False)  # auto-finished after MAX_VIOLATIONS
    score = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} · {self.pack} · {self.score}"


class ExamGoal(models.Model):
    """Daily goal: N new words a day from one pack."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_goal")
    pack = models.ForeignKey(ExamPack, on_delete=models.CASCADE, related_name="goals")
    per_day = models.PositiveSmallIntegerField(default=15)

    def __str__(self):
        return f"{self.user} · {self.pack} · {self.per_day}/day"
