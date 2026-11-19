"""Keep URL secrets (Telegram webhook / reminder cron paths) out of the logs."""

from __future__ import annotations

import logging
import re

_SECRET_PATH = re.compile(r"(/bot/(?:webhook|cron)/)[^\s\"'?]+")


def redact(text: str) -> str:
    return _SECRET_PATH.sub(r"\1<redacted>/", text)


class RedactSecretsFilter(logging.Filter):
    """Redacts secret URL paths in log records (message, args and request path)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        if "/bot/" in msg:
            record.msg = redact(msg)
            record.args = None
        return True
