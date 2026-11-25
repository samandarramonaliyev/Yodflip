"""Optional in-app scheduler. Off unless ALWAYS_ON_SCHEDULER=true (an instance that never sleeps).

Every gunicorn worker runs this small loop; a slot row in the database lets exactly one worker do each
run. The work is jobs.services.run_all, the same function as the cron URLs.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

from . import locks
from .services import run_all

log = logging.getLogger(__name__)
CHECK_EVERY = 30  # seconds
SLOT = "scheduler"
_thread: threading.Thread | None = None


def slot_for(now: datetime) -> str:
    """Start of the current interval in UTC, e.g. 2026-03-02T14:10 (sorts as text)."""
    now = now.astimezone(UTC)
    return now.replace(minute=now.minute - now.minute % settings.SCHEDULER_EVERY_MINUTES).strftime("%Y-%m-%dT%H:%M")


def tick() -> bool:
    """True when this call did the run of the current slot."""
    if not locks.take_slot(SLOT, slot_for(timezone.now())):
        return False
    run_all("scheduler")
    return True


def _loop() -> None:
    pause = threading.Event()
    while True:
        try:
            close_old_connections()
            tick()
        except Exception:
            log.exception("Scheduler tick failed")
            connection.close()
        pause.wait(CHECK_EVERY)


def start() -> threading.Thread | None:
    """Called once per gunicorn worker (gunicorn.conf.py)."""
    global _thread
    if not settings.ALWAYS_ON_SCHEDULER:
        return None
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_loop, name="yodflip-scheduler", daemon=True)
        _thread.start()
        log.info("In-app scheduler started (every %d min)", settings.SCHEDULER_EVERY_MINUTES)
    return _thread
