from django.db import models


class CronRunLog(models.Model):
    """One run of one job (quiz, reminders, broadcasts, duels)."""

    job = models.CharField(max_length=20)
    trigger = models.CharField(max_length=10, default="cron")  # cron | scheduler
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    matched = models.PositiveIntegerField(default=0)
    sent = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)  # incl. blocked and retry_later
    skipped = models.JSONField(default=dict, blank=True)  # {reason: users}
    details = models.JSONField(default=dict, blank=True)  # blocked, retry_later, remaining, errors
    error = models.TextField(blank=True)  # the job itself crashed or could not run

    class Meta:
        ordering = ("-started_at", "-id")
        indexes = [models.Index(fields=["job", "-started_at"], name="cronrun_job_started")]

    def __str__(self):
        return f"{self.job} {self.started_at:%Y-%m-%d %H:%M} sent={self.sent}"


class JobLock(models.Model):
    """One row per job. Taken with a conditional UPDATE, which also works behind PgBouncer
    (Neon's pooled URL), where session advisory locks do not."""

    name = models.CharField(max_length=40, unique=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=32, blank=True)
    last_slot = models.CharField(max_length=20, blank=True)  # last scheduler slot that was run

    def __str__(self):
        return self.name
