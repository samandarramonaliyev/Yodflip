"""The one job behind /bot/cron/<secret>/, /bot/cron/<secret>/quiz/ and the in-app scheduler."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts.models import User
from botquiz.models import QuizSettings
from core.logging import redact

from . import locks
from .models import CronRunLog

log = logging.getLogger(__name__)
LOCK = "run_all"
LOCK_SECONDS = 300
TOTAL_BUDGET = 24  # seconds; cron-job.org stops waiting after 30
QUIZ_BUDGET = 14
KEEP = timedelta(days=14)
RUNS_SHOWN = 7
JOBS = ("quiz", "reminders", "broadcasts", "duels", "classes")
NO_TOKEN = "bot_disabled"


def run_logged(job: str, trigger: str, func) -> dict:
    """Run one part, save a CronRunLog, never raise (a broken part must not stop the others)."""
    row = CronRunLog(job=job, trigger=trigger, started_at=timezone.now())
    try:
        stats = func()
        row.error = stats.get("detail", "")
    except Exception as exc:
        log.exception("Job %s crashed", job)
        stats = {"due": 0, "sent": 0}
        row.error = redact(f"{type(exc).__name__}: {exc}")[:500]
    row.finished_at = timezone.now()
    row.matched, row.sent = stats.get("due", 0), stats.get("sent", 0)
    row.failed = sum(stats.get(k, 0) for k in ("failed", "blocked", "retry_later"))
    row.skipped = stats.get("skipped") or {}
    row.details = {k: stats[k] for k in ("blocked", "retry_later", "remaining", "errors") if stats.get(k)}
    row.save()
    numbers = (row.matched, row.sent, row.failed, row.skipped, row.details)
    log.log(
        logging.ERROR if row.error else logging.INFO,
        "Job %s (%s): matched=%d sent=%d failed=%d skipped=%s details=%s error=%s",
        job,
        trigger,
        *numbers,
        row.error or "-",
    )
    if row.error:
        stats["error"] = row.error
    return stats


def _parts(deadline: float):
    from botquiz.sender import send_due_quizzes
    from broadcasts.services import run_scheduled
    from classes.reminders import send_due as class_reminders
    from duels.services import expire_due
    from telegram_bot.reminders import send_due_reminders

    def bot(func):
        return func if settings.TELEGRAM_BOT_TOKEN else lambda: {"due": 0, "sent": 0, "detail": NO_TOKEN}

    def left() -> float:
        return max(1.0, deadline - time.monotonic())

    def duels() -> dict:
        n = expire_due()
        return {"due": n, "sent": n}

    return [
        ("quiz", bot(lambda: send_due_quizzes(budget=min(QUIZ_BUDGET, left())))),
        ("reminders", bot(lambda: send_due_reminders(budget=left()))),
        ("broadcasts", bot(run_scheduled)),
        ("duels", duels),
        ("classes", bot(lambda: class_reminders(budget=min(8, left())))),
    ]


def run_all(trigger: str = "cron") -> dict:
    """Idempotent: each part claims every user before sending. Overlapping runs are skipped by the lock."""
    token = locks.acquire(LOCK, LOCK_SECONDS)
    if token is None:
        log.info("Job run skipped (%s): another run is in progress", trigger)
        return {"ok": True, "sent": 0, "detail": "already_running"}
    try:
        deadline = time.monotonic() + TOTAL_BUDGET
        out = {name: run_logged(name, trigger, func) for name, func in _parts(deadline)}
        CronRunLog.objects.filter(started_at__lt=timezone.now() - KEEP).delete()
    finally:
        locks.release(LOCK, token)
    errors = [p["error"] for p in out.values() if p.get("error") not in (None, NO_TOKEN)]
    result = {"ok": not errors, "sent": out["quiz"].get("sent", 0) + out["reminders"].get("sent", 0), **out}
    if not settings.TELEGRAM_BOT_TOKEN:
        result["detail"] = NO_TOKEN
    return result


def _iso(dt) -> str:
    return timezone.localtime(dt).isoformat(timespec="seconds")


def _run_dict(r: CronRunLog) -> dict:
    return {
        "at": _iso(r.started_at),
        "trigger": r.trigger,
        "matched": r.matched,
        "sent": r.sent,
        "failed": r.failed,
        "skipped": sum(r.skipped.values()),
        "skip_reasons": r.skipped,
        "details": r.details,
        "error": r.error,
    }


def status_report() -> dict:
    tg = User.objects.filter(telegram_id__isnull=False)
    quiz = QuizSettings.objects.filter(user__telegram_id__isnull=False)
    last = CronRunLog.objects.first()
    jobs = {}
    for job in JOBS:
        rows = CronRunLog.objects.filter(job=job)
        runs = [_run_dict(r) for r in rows[:RUNS_SHOWN]]
        matched = rows.filter(matched__gt=0).first()
        jobs[job] = {
            "last_run": runs[0]["at"] if runs else None,
            "last_run_with_matches": _run_dict(matched) if matched else None,
            "runs": runs,
        }
    return {
        "ok": True,
        "now": _iso(timezone.now()),
        "timezone": settings.TIME_ZONE,
        "bot_token_set": bool(settings.TELEGRAM_BOT_TOKEN),
        "public_url_https": settings.PUBLIC_URL.startswith("https://"),
        "always_on_scheduler": settings.ALWAYS_ON_SCHEDULER,
        "last_run": _iso(last.started_at) if last else None,
        "minutes_since_last_run": int((timezone.now() - last.started_at).total_seconds() // 60) if last else None,
        "users": {
            "with_telegram": tg.count(),
            "reminder_enabled": tg.filter(reminder_time__isnull=False).count(),
            "quiz_enabled": quiz.filter(enabled=True).count(),
            "bot_blocked": quiz.filter(bot_blocked=True).count(),
        },
        "jobs": jobs,
    }
