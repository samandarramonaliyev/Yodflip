import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from botquiz.services import mark_reachable
from jobs.services import run_all, status_report

from . import services
from .bot import process_update

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
        _note_reachable(update)
        process_update(update)
    except Exception:  # noqa: BLE001 - always 200 so Telegram doesn't retry forever
        log.exception("Failed to process Telegram update %s", update.get("update_id"))
    return HttpResponse("ok")


def _note_reachable(update: dict) -> None:
    """Any private message or button press proves that the bot can write to this user (again)."""
    part = update.get("callback_query") or update.get("message") or {}
    chat = (part.get("message") or part).get("chat") or {}
    sender = (part.get("from") or {}).get("id")
    if sender and chat.get("type") == "private":
        mark_reachable(sender)


def _client_ip(request) -> str:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")


def _cron_allowed(request, secret: str) -> bool:
    if not services.cron_secret_matches(secret):
        # Log why, never the secret itself.
        log.warning(
            "Cron 403: secret mismatch (given length %d; BOT_CRON_SECRET %s, expected length %d) from %s",
            len((secret or "").strip()),
            "set" if (settings.BOT_CRON_SECRET or "").strip() else "NOT set (using value derived from SECRET_KEY)",
            len(services.cron_secret()),
            _client_ip(request),
        )
        return False
    return True


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cron(request, secret: str):
    """/bot/cron/<BOT_CRON_SECRET>/ and /bot/cron/<BOT_CRON_SECRET>/quiz/ (trailing slash optional).

    Both run the same job (quiz, reminders, scheduled broadcasts, expired duels). Every part sends at
    most once per user and day, so calling it often, or from several schedulers, is safe. A call every
    10 minutes also keeps a free Render service awake. The secret in the path is the only check.
    """
    if not _cron_allowed(request, secret):
        return HttpResponseForbidden("forbidden")
    return JsonResponse(run_all("cron"))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cron_status(request, secret: str):
    """/bot/cron/<BOT_CRON_SECRET>/status/: the last runs. Sends nothing."""
    if not _cron_allowed(request, secret):
        return HttpResponseForbidden("forbidden")
    return JsonResponse(status_report())
