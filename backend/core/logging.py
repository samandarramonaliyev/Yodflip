"""Keep URL secrets (Telegram webhook / reminder cron paths) and bot tokens out of the logs."""

from __future__ import annotations

import logging
import re

_SECRET_PATH = re.compile(r"(/bot/(?:webhook|cron)/)[^\s\"'?]+")
_BOT_TOKEN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{20,}")


def redact(text: str) -> str:
    return _BOT_TOKEN.sub("<bot-token>", _SECRET_PATH.sub(r"\1<redacted>/", text))


class RedactSecretsFilter(logging.Filter):
    """Redacts secret URL paths and bot tokens in log records (message and args)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        clean = redact(msg)
        if clean != msg:
            record.msg = clean
            record.args = None
        return True


class RedactingFormatter(logging.Formatter):
    """Also cleans tracebacks, which a filter never sees."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
