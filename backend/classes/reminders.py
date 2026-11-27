"""Bot reminder 24h before an assignment deadline (part of the hourly cron job, idempotent)."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from telegram_bot.notify import Note, send_notes

from . import services as S
from .models import Assignment, AssignmentReminder, Membership

WINDOW = timedelta(hours=24)


def _claim(assignment_id: int, user_id: int):
    def claim() -> bool:
        try:
            with transaction.atomic():
                AssignmentReminder.objects.create(assignment_id=assignment_id, user_id=user_id)
            return True
        except IntegrityError:
            return False

    return claim


def _release(assignment_id: int, user_id: int):
    return lambda: AssignmentReminder.objects.filter(assignment_id=assignment_id, user_id=user_id).delete()


def due_notes(now=None) -> tuple[list[Note], dict]:
    """Students with an unfinished assignment whose deadline is in the next 24 hours, not reminded yet."""
    from telegram_bot.texts import t

    now = now or timezone.now()
    skipped: Counter = Counter()
    notes: list[Note] = []
    qs = Assignment.objects.filter(
        due_at__gt=now, due_at__lte=now + WINDOW, classroom__archived=False, starts_on__lte=timezone.localdate(now)
    ).select_related("classroom", "deck")
    for a in qs:
        ids = list(
            Membership.objects.filter(classroom=a.classroom, status=Membership.ACTIVE)
            .exclude(user_id__in=AssignmentReminder.objects.filter(assignment=a).values("user_id"))
            .values_list("user_id", flat=True)
        )
        if not ids:
            continue
        progress = S.progress(a, ids, now)
        users = User.objects.filter(pk__in=ids).select_related("quiz_settings")
        for u in users:
            if progress[u.id]["status"] == "done":
                skipped["completed"] += 1
                continue
            if not u.telegram_id or not u.is_active:
                skipped["no_telegram"] += 1
                continue
            if not u.notify_classes:
                skipped["notifications_off"] += 1
                continue
            conf = getattr(u, "quiz_settings", None)
            if conf and conf.bot_blocked:
                skipped["bot_blocked"] += 1
                continue
            hours = max(1, round((a.due_at - now).total_seconds() / 3600))
            text = t(u.ui_language, "class_deadline", title=a.title, cls=a.classroom.name, hours=hours)
            notes.append(
                Note(
                    u.id,
                    u.telegram_id,
                    text,
                    t(u.ui_language, "class_open"),
                    f"/classes/{a.classroom_id}",
                    _claim(a.id, u.id),
                    _release(a.id, u.id),
                )
            )
    return notes, dict(skipped)


def send_due(budget: float = 10) -> dict:
    notes, skipped = due_notes()
    return send_notes(notes, budget, skipped)
