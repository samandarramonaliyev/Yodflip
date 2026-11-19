import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from . import services
from .bot import process_update, send_reminders

log = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def webhook(request, secret: str):
    """Telegram → POST /bot/webhook/<secret>/ (path secret + X-Telegram-Bot-Api-Secret-Token header)."""
    expected = services.webhook_secret()
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not settings.TELEGRAM_BOT_TOKEN or not (
        hmac.compare_digest(secret, expected) and hmac.compare_digest(header, expected)
    ):
        return HttpResponseForbidden()
    try:
        update = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    try:
        process_update(update)
    except Exception:  # noqa: BLE001 - always 200 so Telegram doesn't retry forever
        log.exception("Failed to process Telegram update %s", update.get("update_id"))
    return HttpResponse("ok")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cron(request, secret: str):
    """Send due daily reminders. Call every 5–15 min from an external scheduler (e.g. cron-job.org).

    Also keeps a free Render service awake.
    """
    if not hmac.compare_digest(secret, services.cron_secret()):
        return HttpResponseForbidden()
    if not settings.TELEGRAM_BOT_TOKEN:
        return JsonResponse({"ok": True, "sent": 0, "detail": "bot_disabled"})
    users = services.take_due_reminders()
    sent = send_reminders(users)
    return JsonResponse({"ok": True, "due": len(users), "sent": sent})
