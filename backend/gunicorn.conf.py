"""gunicorn config. On startup (once, in the master) the Telegram webhook is registered."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 120
accesslog = "-"
forwarded_allow_ips = "*"

try:  # mask /bot/webhook/<secret>/ and /bot/cron/<secret>/ in the access log
    from gunicorn.glogging import Logger

    class RedactingLogger(Logger):
        def access(self, resp, req, environ, request_time):
            from core.logging import redact

            for key in ("RAW_URI", "PATH_INFO"):
                if key in environ:
                    environ[key] = redact(environ[key])
            req.uri = redact(getattr(req, "uri", "") or "")
            req.path = redact(getattr(req, "path", "") or "")
            super().access(resp, req, environ, request_time)

    logger_class = RedactingLogger
except ImportError:  # gunicorn not installed (e.g. Windows dev)
    pass


def when_ready(server):
    try:
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()
        from telegram_bot.setup import configure_telegram

        configure_telegram()
    except Exception as exc:  # noqa: BLE001 - never block startup on Telegram
        server.log.error("Telegram setup failed: %s", exc)
