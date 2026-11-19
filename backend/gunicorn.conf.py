"""gunicorn config. On startup (once, in the master) the Telegram webhook is registered."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 120
accesslog = "-"
forwarded_allow_ips = "*"


def when_ready(server):
    try:
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        from telegram_bot.setup import configure_telegram

        configure_telegram()
    except Exception as exc:  # noqa: BLE001 - never block startup on Telegram
        server.log.error("Telegram setup failed: %s", exc)
