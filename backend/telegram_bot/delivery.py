"""One way to send a message to one user, shared by the reminders, the quiz and the broadcasts.

The outcome says whether the message may have been delivered, so callers know if a second try is safe.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)

from core.logging import redact

PACE = 1 / 25  # at most 25 messages per second
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10

SENT = "sent"
BLOCKED = "blocked"  # the bot can't write to this user
REJECTED = "rejected"  # Telegram refused this message: not delivered, retrying won't help
RETRY_LATER = "retry_later"  # certainly not delivered, a later try is safe
FATAL = "fatal"  # nothing can be sent at all (wrong bot token)
FAILED = "failed"  # unknown (e.g. timeout): maybe delivered, so never send it again

STAT_KEY = {SENT: SENT, BLOCKED: BLOCKED, REJECTED: FAILED, RETRY_LATER: RETRY_LATER, FATAL: FAILED, FAILED: FAILED}
UNREACHABLE = ("chat not found", "user is deactivated", "peer_id_invalid", "can't initiate")


class Outcome(NamedTuple):
    status: str
    detail: str = ""
    result: Any = None


def new_stats(due: int, skipped: dict) -> dict:
    stats = {"due": due, "skipped": skipped, "errors": {}}
    return stats | dict.fromkeys(("sent", "blocked", "failed", "retry_later", "remaining"), 0)


def count_error(stats: dict, text: str) -> None:
    stats["errors"][text] = stats["errors"].get(text, 0) + 1


def error_text(exc: BaseException) -> str:
    return redact(f"{type(exc).__name__}: {exc}")[:300]


async def deliver(
    send: Callable[[], Awaitable[Any]],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    deadline: float | None = None,
) -> Outcome:
    """Never raises. Waits out 429 (`retry_after`) unless that would pass `deadline` (time.monotonic())."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return Outcome(SENT, "", await send())
        except TelegramRetryAfter as exc:
            if attempt == MAX_RETRIES or (deadline is not None and time.monotonic() + exc.retry_after > deadline):
                break
            await sleep(exc.retry_after)
        except TelegramForbiddenError as exc:
            return Outcome(BLOCKED, error_text(exc))
        except (TelegramUnauthorizedError, TelegramNotFound) as exc:
            return Outcome(FATAL, error_text(exc))
        except TelegramBadRequest as exc:
            gone = any(s in str(exc).lower() for s in UNREACHABLE)
            return Outcome(BLOCKED if gone else REJECTED, error_text(exc))
        except TelegramNetworkError as exc:
            # No connection at all = certainly not delivered; a timeout may have been delivered.
            return Outcome(RETRY_LATER if "ClientConnector" in str(exc) else FAILED, error_text(exc))
        except Exception as exc:  # noqa: BLE001 - one user must never stop the run
            return Outcome(FAILED, error_text(exc))
    return Outcome(RETRY_LATER, "429 too many requests")
