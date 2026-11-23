"""Register the webhook, commands and the Mini App menu button with Telegram (called on startup)."""

from __future__ import annotations

import logging

import httpx
from django.conf import settings

from . import services

log = logging.getLogger(__name__)

COMMANDS = [
    {"command": "start", "description": "Open Yodflip"},
    {"command": "daily", "description": "Today's challenge"},
    {"command": "quiz", "description": "Quick quiz in the chat (/quiz settings)"},
    {"command": "duel", "description": "Challenge a friend"},
    {"command": "stats", "description": "My progress"},
    {"command": "review", "description": "Words due for review"},
    {"command": "remind", "description": "Daily reminder: /remind 19:00 or off"},
]


def webhook_url() -> str:
    return services.webapp_url(f"/bot/webhook/{services.webhook_secret()}/")


def configure_telegram(client: httpx.Client | None = None) -> bool:
    """Idempotent. Returns True when the webhook was set. Never raises (logs instead)."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        log.info("TELEGRAM_BOT_TOKEN not set: Telegram bot disabled.")
        return False
    url = webhook_url()
    if not url.startswith("https://"):
        log.warning("PUBLIC_URL %r is not HTTPS: Telegram webhook not set.", settings.PUBLIC_URL)
        return False
    api = f"https://api.telegram.org/bot{token}"
    own_client = client is None
    client = client or httpx.Client(timeout=15)
    try:
        r = client.post(
            f"{api}/setWebhook",
            json={
                "url": url,
                "secret_token": services.webhook_secret(),
                "allowed_updates": ["message", "callback_query"],
                "max_connections": 20,
            },
        )
        r.raise_for_status()
        client.post(f"{api}/setMyCommands", json={"commands": COMMANDS})
        client.post(
            f"{api}/setChatMenuButton",
            json={"menu_button": {"type": "web_app", "text": "Play", "web_app": {"url": services.webapp_url("/")}}},
        )
        log.info("Telegram webhook set to %s", url.replace(services.webhook_secret(), "<secret>"))
        return True
    except httpx.HTTPError as exc:
        log.error("Could not configure Telegram webhook: %s", exc)
        return False
    finally:
        if own_client:
            client.close()
