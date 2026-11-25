from __future__ import annotations

import uuid
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import JobLock


def acquire(name: str, seconds: int) -> str | None:
    """A token when the lock was free (or its owner died and it ran out), else None."""
    JobLock.objects.get_or_create(name=name)
    now, token = timezone.now(), uuid.uuid4().hex
    free = JobLock.objects.filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now), name=name)
    return token if free.update(locked_until=now + timedelta(seconds=seconds), token=token) else None


def release(name: str, token: str) -> None:
    JobLock.objects.filter(name=name, token=token).update(locked_until=None, token="")


def take_slot(name: str, slot: str) -> bool:
    """True for exactly one caller per slot (e.g. "2026-03-02T19:10"), whatever the number of workers."""
    JobLock.objects.get_or_create(name=name)
    return bool(JobLock.objects.filter(name=name, last_slot__lt=slot).update(last_slot=slot))


def renew(name: str, token: str, seconds: int) -> bool:
    """False = the lock was lost (it ran out and somebody else took it)."""
    until = timezone.now() + timedelta(seconds=seconds)
    return bool(JobLock.objects.filter(name=name, token=token).update(locked_until=until))


def holder(name: str) -> str:
    """Token of the current owner, "" when the lock is free."""
    row = JobLock.objects.filter(name=name, locked_until__gt=timezone.now()).first()
    return row.token if row else ""
