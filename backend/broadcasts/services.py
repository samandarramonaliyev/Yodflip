"""Audience, background sending and resuming.

Never twice to the same user: recipients are written down once, every row is claimed
(pending → sending) with a conditional UPDATE before the message goes out, and a row left in
"sending" by a killed process is never sent again (Telegram may already have delivered it).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import timedelta

from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from asgiref.sync import async_to_sync, sync_to_async
from django.db import close_old_connections, connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from botquiz.services import mark_blocked
from gamification.services import today
from jobs import locks
from telegram_bot import delivery

from .content import render
from .models import Broadcast, BroadcastDelivery

log = logging.getLogger(__name__)
LOCK = "broadcast"  # one running broadcast at a time: together they stay below 25 messages / s
LOCK_SECONDS = 120  # without a heartbeat for this long the broadcast can be resumed
HEARTBEAT = 2  # seconds
BATCH = 50
PHOTO_TIMEOUT = 30
D = BroadcastDelivery


# --------------------------------------------------------------------------- audience
def audience(key: str):
    qs = User.objects.filter(telegram_id__isnull=False, is_active=True).exclude(quiz_settings__bot_blocked=True)
    day = today()
    if key in ("en", "de"):
        return qs.filter(active_track=key)
    if key == "active7":
        return qs.filter(last_active_date__gte=day - timedelta(days=6))
    if key == "inactive3":
        never = Q(last_active_date__isnull=True, date_joined__lte=timezone.now() - timedelta(days=3))
        return qs.filter(never | Q(last_active_date__lte=day - timedelta(days=3)))
    if key == "not_today":
        return qs.exclude(last_active_date=day)
    if key == "web":
        return qs.filter(email__isnull=False).exclude(email="")
    if key == "all":
        return qs
    raise ValueError(key)


# --------------------------------------------------------------------------- one message
def markup_for(b: Broadcast) -> InlineKeyboardMarkup | None:
    if b.button_kind == "url":
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b.button_text, url=b.button_url)]])
    if b.button_kind == "webapp":
        from telegram_bot.handlers import open_button

        return open_button(b.button_text, "/")
    return None


class Message:
    """The content of a broadcast, ready to be sent to many users."""

    def __init__(self, b: Broadcast, photo: bytes | None = None):
        self.b, self.photo, self.file_id = b, photo, b.photo_file_id
        self.markup = markup_for(b)
        if b.photo and photo is None and not self.file_id:
            with b.photo.open("rb") as f:
                self.photo = f.read()

    async def send(self, bot, chat_id: int, text: str):
        kw = {"reply_markup": self.markup, "parse_mode": "HTML"}
        if not (self.photo or self.file_id):
            return await bot.send_message(chat_id, text, request_timeout=delivery.REQUEST_TIMEOUT, **kw)
        photo = self.file_id or BufferedInputFile(self.photo, "photo.jpg")
        result = await bot.send_photo(chat_id, photo, caption=text, request_timeout=PHOTO_TIMEOUT, **kw)
        sizes = getattr(result, "photo", None)
        if sizes and not self.file_id:
            self.file_id = sizes[-1].file_id  # no further uploads
        return result


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def send_test(b: Broadcast, user: User, photo: bytes | None = None) -> delivery.Outcome:
    """Only to this user (the admin). Nothing is stored."""
    from telegram_bot.bot import make_bot

    message, text = Message(b, photo), render(b.text, user)

    async def run():
        bot = make_bot()
        try:
            return await delivery.deliver(
                lambda: message.send(bot, user.telegram_id, text), sleep, time.monotonic() + 20
            )
        finally:
            await bot.session.close()

    return async_to_sync(run)()


# --------------------------------------------------------------------------- lifecycle
def is_stalled(b: Broadcast) -> bool:
    """Marked as running, but its thread is gone (restart, sleep, crash)."""
    return b.status == Broadcast.RUNNING and locks.holder(LOCK) != b.runner


def take(pk: int) -> str | None:
    """Become the runner of this broadcast. None = another broadcast is running, or nothing to do."""
    token = locks.acquire(LOCK, LOCK_SECONDS)
    if token is None:
        return None
    startable = [Broadcast.QUEUED, Broadcast.SCHEDULED, Broadcast.PAUSED, Broadcast.RUNNING]  # RUNNING = stalled
    if not Broadcast.objects.filter(pk=pk, status__in=startable).update(
        status=Broadcast.RUNNING, runner=token, error="", finished_at=None
    ):
        locks.release(LOCK, token)
        return None
    Broadcast.objects.filter(pk=pk, started_at__isnull=True).update(started_at=timezone.now())
    return token


def start(pk: int) -> bool:
    token = take(pk)
    if token is None:
        return False
    spawn(pk, token)
    return True


def spawn(pk: int, token: str) -> None:
    threading.Thread(target=_thread, args=(pk, token), name=f"broadcast-{pk}", daemon=True).start()


def _thread(pk: int, token: str) -> None:
    close_old_connections()
    try:
        run(pk, token)
    finally:
        connection.close()


def stop(pk: int, status: str) -> bool:
    """PAUSED or CANCELLED. A running thread notices it at its next heartbeat."""
    allowed = {
        Broadcast.PAUSED: [Broadcast.RUNNING],
        Broadcast.CANCELLED: [Broadcast.QUEUED, Broadcast.SCHEDULED, Broadcast.PAUSED, Broadcast.RUNNING],
    }[status]
    return bool(Broadcast.objects.filter(pk=pk, status__in=allowed).update(status=status))


def run_scheduled() -> dict:
    """Part of the cron job: start the next due or queued broadcast (the sending runs in a thread)."""
    due = Broadcast.objects.filter(
        Q(status=Broadcast.QUEUED) | Q(status=Broadcast.SCHEDULED, scheduled_at__lte=timezone.now())
    ).order_by("scheduled_at", "id")
    ids = list(due.values_list("pk", flat=True))
    started = bool(ids) and start(ids[0])
    waiting = len(ids) - int(started)
    return {"due": len(ids), "sent": 0, "skipped": {"waiting": waiting} if waiting else {}}


# --------------------------------------------------------------------------- sending
def prepare(pk: int) -> None:
    """Write down the recipients, once. Rows a dead process left in "sending" may have been delivered."""
    with transaction.atomic():
        b = Broadcast.objects.select_for_update().get(pk=pk)
        if not b.prepared:
            ids = audience(b.audience).values_list("pk", flat=True)
            rows = [D(broadcast=b, user_id=i) for i in ids]
            D.objects.bulk_create(rows, batch_size=500, ignore_conflicts=True)
            b.total, b.prepared = len(rows), True
            b.save(update_fields=["total", "prepared"])
    D.objects.filter(broadcast_id=pk, status=D.SENDING).update(
        status=D.FAILED, error="interrupted: maybe delivered, not sent again"
    )


def refresh_counts(pk: int) -> None:
    n = D.objects.filter(broadcast_id=pk).aggregate(
        sent=Count("id", filter=Q(status=D.SENT)),
        failed=Count("id", filter=Q(status__in=[D.FAILED, D.BLOCKED])),
    )
    Broadcast.objects.filter(pk=pk).update(**n)


def heartbeat(pk: int, token: str) -> bool:
    """False = stop: paused, cancelled, or the lock was lost."""
    refresh_counts(pk)
    alive = locks.renew(LOCK, token, LOCK_SECONDS)
    return alive and Broadcast.objects.filter(pk=pk, status=Broadcast.RUNNING, runner=token).exists()


def claim(row: D, text: str) -> str | None:
    """The personal text, when this row is ours to send."""
    user = row.user
    if not user.telegram_id or not user.is_active:
        D.objects.filter(pk=row.pk, status=D.PENDING).update(status=D.FAILED, error="unreachable")
        return None
    personal = render(text, user)
    won = D.objects.filter(pk=row.pk, status=D.PENDING).update(status=D.SENDING, updated_at=timezone.now())
    return personal if won else None


def finish_row(row: D, out: delivery.Outcome) -> None:
    status = {delivery.SENT: D.SENT, delivery.BLOCKED: D.BLOCKED}.get(out.status, D.FAILED)
    if out.status in (delivery.RETRY_LATER, delivery.FATAL):
        status = D.PENDING  # certainly not delivered
    if out.status == delivery.BLOCKED:
        mark_blocked(row.user_id)
    if out.status != delivery.SENT:
        log.info("Broadcast %s to user %s: %s (%s)", row.broadcast_id, row.user_id, out.status, out.detail)
    D.objects.filter(pk=row.pk).update(status=status, error=out.detail[:300], updated_at=timezone.now())


def next_batch(pk: int) -> list[D]:
    return list(D.objects.filter(broadcast_id=pk, status=D.PENDING).select_related("user").order_by("id")[:BATCH])


async def _send_all(pk: int, token: str, b: Broadcast, message: Message) -> str | None:
    """Error text when the sending has to pause, "" when everything is done, None when it was stopped."""
    from telegram_bot.bot import make_bot

    beat = sync_to_async(heartbeat)
    last = time.monotonic()

    async def patient_sleep(seconds: float) -> None:
        """A long 429 wait keeps the lock alive."""
        while seconds > 0:
            await sleep(min(seconds, 10))
            seconds -= 10
            await beat(pk, token)

    bot = make_bot()
    try:
        while batch := await sync_to_async(next_batch)(pk):
            if not await beat(pk, token):
                return None
            for row in batch:
                if time.monotonic() - last > HEARTBEAT:
                    last = time.monotonic()
                    if not await beat(pk, token):
                        return None
                try:
                    text = await sync_to_async(claim)(row, b.text)
                except Exception as exc:  # one broken account must not stop the broadcast
                    log.exception("Broadcast %s: user %s could not be prepared", pk, row.user_id)
                    await sync_to_async(finish_row)(row, delivery.Outcome(delivery.FAILED, delivery.error_text(exc)))
                    continue
                if text is None:
                    continue

                async def send(chat_id=row.user.telegram_id, text=text):
                    return await message.send(bot, chat_id, text)

                out = await delivery.deliver(send, patient_sleep)
                await sync_to_async(finish_row)(row, out)
                if out.status in (delivery.RETRY_LATER, delivery.FATAL):
                    return out.detail or out.status
                if message.file_id and message.file_id != b.photo_file_id:
                    b.photo_file_id = message.file_id
                    await sync_to_async(Broadcast.objects.filter(pk=pk).update)(photo_file_id=message.file_id)
                await sleep(delivery.PACE)
        return ""
    finally:
        await bot.session.close()


def run(pk: int, token: str) -> None:
    """Send everything that is still pending. Runs in a background thread, never raises."""
    mine = Broadcast.objects.filter(pk=pk, runner=token, status=Broadcast.RUNNING)
    try:
        prepare(pk)
        b = Broadcast.objects.get(pk=pk)
        error = async_to_sync(_send_all)(pk, token, b, Message(b))
        refresh_counts(pk)
        if error == "":
            mine.update(status=Broadcast.DONE, finished_at=timezone.now())
        elif error:
            mine.update(status=Broadcast.PAUSED, error=error[:300])
    except Exception as exc:
        log.exception("Broadcast %s stopped", pk)
        mine.update(status=Broadcast.PAUSED, error=delivery.error_text(exc))
    finally:
        locks.release(LOCK, token)
    b = Broadcast.objects.filter(pk=pk).first()
    if b:
        log.info("Broadcast %s: status=%s total=%d sent=%d failed=%d", pk, b.status, b.total, b.sent, b.failed)
