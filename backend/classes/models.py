"""Classes (teacher mode): organizations, classes, members, assignments."""

import secrets

from django.conf import settings
from django.db import models

from accounts.models import CEFR_CHOICES, TRACK_CHOICES

PLANS = [("free", "Free"), ("pro", "Pro")]
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I: easy to read aloud and type
COLORS = ["#6C5CE7", "#FDCB6E", "#00B894", "#FF7675", "#0984E3", "#E17055", "#A29BFE", "#2D3436"]


def new_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def new_join_code() -> str:
    return new_code(6)


def new_teacher_code() -> str:
    return new_code(10)


class Organization(models.Model):
    """A learning center. Created by the site admin; its admins see all its classes."""

    name = models.CharField(max_length=120)
    plan = models.CharField(max_length=10, choices=PLANS, default="free")
    # 0 = the plan's default (settings.CLASS_LIMITS)
    max_classes = models.PositiveIntegerField(default=0)
    max_students = models.PositiveIntegerField(default=0)
    admins = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="org_admin_of")
    teachers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="org_teacher_of")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Classroom(models.Model):
    org = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.SET_NULL, related_name="classes")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_classes")
    name = models.CharField(max_length=80)
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES, blank=True)
    description = models.CharField(max_length=500, blank=True)
    color = models.CharField(max_length=7, default=COLORS[0])
    join_code = models.CharField(max_length=6, unique=True, default=new_join_code)
    teacher_code = models.CharField(max_length=10, unique=True, default=new_teacher_code)  # co-teacher invite
    approval_required = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)
    plan = models.CharField(max_length=10, choices=PLANS, default="free")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "class"
        verbose_name_plural = "classes"

    def __str__(self):
        return f"{self.name} ({self.join_code})"


class CoTeacher(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="co_teachers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="co_teaching")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["classroom", "user"], name="uniq_coteacher")]


class Membership(models.Model):
    PENDING, ACTIVE, REMOVED, LEFT = "pending", "active", "removed", "left"
    STATUSES = [(s, s) for s in (PENDING, ACTIVE, REMOVED, LEFT)]

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_memberships")
    status = models.CharField(max_length=8, choices=STATUSES, default=ACTIVE)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["classroom", "user"], name="uniq_membership")]
        indexes = [models.Index(fields=["classroom", "status"], name="membership_status")]


class Assignment(models.Model):
    LEVEL, EXAM, DECK = "level", "exam", "deck"
    KINDS = [(LEVEL, "Level"), (EXAM, "Exam pack"), (DECK, "Deck")]
    LEARN, PLAYS = "learn_pct", "plays"
    TARGETS = [(LEARN, "Learn N% of the words"), (PLAYS, "Play at least N times")]

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="assignments")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=5, choices=KINDS)
    level = models.CharField(max_length=2, choices=CEFR_CHOICES, blank=True)
    lesson_from = models.PositiveSmallIntegerField(null=True, blank=True)
    lesson_to = models.PositiveSmallIntegerField(null=True, blank=True)
    exam_slug = models.CharField(max_length=60, blank=True)
    topics = models.JSONField(default=list, blank=True)
    deck = models.ForeignKey("decks.Deck", null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments")
    # Built-in words of a level / pack assignment, frozen when it is created (the content is stable).
    word_ids = models.JSONField(default=list, blank=True)
    target_kind = models.CharField(max_length=10, choices=TARGETS, default=LEARN)
    target_value = models.PositiveSmallIntegerField(default=80)
    starts_on = models.DateField()
    due_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("due_at", "id")


class AssignmentReminder(models.Model):
    """One row = the 24h deadline reminder was claimed for this student (created before sending)."""

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="reminders")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=12, default="claimed")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assignment", "user"], name="uniq_assignment_reminder")]


class Announcement(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="announcements")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    text = models.TextField(max_length=2000)
    broadcast = models.ForeignKey("broadcasts.Broadcast", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
