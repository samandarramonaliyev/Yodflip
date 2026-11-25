import uuid

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from jobs.models import CronRunLog
from telegram_bot import delivery

from . import services
from .content import DEFAULT_NAME, check_html, current_streak
from .models import AUDIENCES, Broadcast

HISTORY = 20
MAX_PHOTO = 5 * 1024 * 1024
PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}
TEMPLATES = [
    {
        "name": "Kunlik eslatma",
        "text": "🔥 Bugun hali so'z yodlamadingiz! 5 daqiqa vaqt ajrating 👇",
        "button_text": "🎮 Boshlash",
        "audience": "not_today",
    },
    {
        "name": "Takrorlash vaqti",
        "text": "👋 {name}, takrorlashga <b>{due_words}</b> ta so'z kutmoqda. Seriyangiz: 🔥 {streak} kun!",
        "button_text": "🔁 Takrorlash",
        "audience": "not_today",
    },
    {
        "name": "Yangi funksiya",
        "text": "🎉 <b>Yangi funksiya!</b>\n\n{name}, ilovaga yangilik qo'shildi: ...\n\nHoziroq sinab ko'ring 👇",
        "button_text": "✨ Sinab ko'rish",
        "audience": "all",
    },
    {
        "name": "Haftalik natija",
        "text": "📊 <b>Hafta yakuni</b>\n\n{name}, seriyangiz: 🔥 {streak} kun.\nTakrorlashga: {due_words} ta so'z.\n\n"
        "Yangi haftani kuchli boshlaymiz! 💪",
        "button_text": "📈 Natijalarim",
        "audience": "active7",
    },
]


class BroadcastForm(forms.ModelForm):
    text = forms.CharField(error_messages={"required": "Xabar matni bo'sh"})
    photo = forms.ImageField(required=False, error_messages={"invalid_image": "Rasm fayli yaroqsiz"})
    button_url = forms.URLField(
        required=False, max_length=500, assume_scheme="https", error_messages={"invalid": "Havola noto'g'ri"}
    )
    nonce = forms.UUIDField()
    scheduled_at = forms.DateTimeField(
        required=False, input_formats=["%Y-%m-%dT%H:%M"], error_messages={"invalid": "Vaqt noto'g'ri"}
    )

    class Meta:
        model = Broadcast
        fields = (
            "text",
            "photo",
            "button_kind",
            "button_text",
            "button_url",
            "audience",
            "scheduled_at",
        )  # nonce: see submit()

    def clean_text(self):
        return self.cleaned_data["text"].replace("\r\n", "\n").strip()

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > MAX_PHOTO:
            raise forms.ValidationError("Rasm 5 MB dan kichik bo'lishi kerak")
        if photo and photo.image.format not in PHOTO_FORMATS:
            raise forms.ValidationError("Faqat JPG, PNG yoki WEBP")
        return photo

    def clean(self):
        data = super().clean()
        if data.get("text") and (error := check_html(data["text"], bool(data.get("photo")))):
            self.add_error("text", error)
        kind = data.get("button_kind")
        if kind and not data.get("button_text"):
            self.add_error("button_text", "Tugma matnini yozing")
        if kind == "url" and not data.get("button_url") and "button_url" not in self.errors:
            self.add_error("button_url", "Tugma havolasini yozing")
        return data


def _problem(text: str, status: int = 400):
    return JsonResponse({"ok": False, "error": text}, status=status)


def _dict(b: Broadcast) -> dict:
    stalled = services.is_stalled(b)
    when = b.finished_at or b.started_at or b.scheduled_at or b.created_at
    return {
        "id": b.pk,
        "text": b.text,
        "audience": b.get_audience_display(),
        "by": str(b.created_by or ""),
        "status": "stalled" if stalled else b.status,
        "label": "To'xtab qolgan" if stalled else b.get_status_display(),
        "total": b.total,
        "sent": b.sent,
        "failed": b.failed,
        "error": b.error,
        "when": timezone.localtime(when).strftime("%d.%m.%Y %H:%M"),
        "can_resume": stalled or b.status in (Broadcast.PAUSED, Broadcast.QUEUED),
        "can_pause": b.status == Broadcast.RUNNING and not stalled,
        "can_cancel": b.status not in (Broadcast.DONE, Broadcast.CANCELLED),
    }


@staff_member_required
@ensure_csrf_cookie
@require_GET
def page(request):
    """/admin/broadcast/"""
    user = request.user
    last = CronRunLog.objects.first()
    ctx = {
        **admin.site.each_context(request),
        "title": "📣 Xabar yuborish",
        "audiences": [(k, label, services.audience(k).count()) for k, label in AUDIENCES],
        "templates": TEMPLATES,
        "nonce": uuid.uuid4(),
        "sample": {
            "name": user.display_name or DEFAULT_NAME,
            "streak": current_streak(user),
            "due_words": 12,
        },
        "bot_ready": bool(settings.TELEGRAM_BOT_TOKEN),
        "telegram_linked": bool(user.telegram_id),
        "tz": settings.TIME_ZONE,
        "cron_minutes": int((timezone.now() - last.started_at).total_seconds() // 60) if last else None,
    }
    return render(request, "broadcasts/page.html", ctx)


@staff_member_required
@require_GET
def count(request):
    key = request.GET.get("audience", "")
    if key not in dict(AUDIENCES):
        return _problem("audience")
    return JsonResponse({"count": services.audience(key).count()})


@staff_member_required
@require_GET
def history(request):
    rows = [_dict(b) for b in Broadcast.objects.select_related("created_by")[:HISTORY]]
    return JsonResponse({"items": rows, "busy": any(r["status"] == "running" for r in rows)})


@staff_member_required
@require_POST
def submit(request):
    """action = test (only to me) | send | schedule"""
    action = request.POST.get("action")
    if action not in ("test", "send", "schedule"):
        return _problem("action")
    form = BroadcastForm(request.POST, request.FILES)
    if not form.is_valid():
        return _problem(" · ".join(e for errors in form.errors.values() for e in errors))
    if not settings.TELEGRAM_BOT_TOKEN:
        return _problem("TELEGRAM_BOT_TOKEN o'rnatilmagan")
    b: Broadcast = form.save(commit=False)
    b.nonce = form.cleaned_data["nonce"]
    if action == "test":
        return _test(request, b, form.cleaned_data.get("photo"))
    existing = Broadcast.objects.filter(nonce=b.nonce).first()  # double click / retried request
    if existing:
        return JsonResponse({"ok": True, "id": existing.pk, "duplicate": True})
    if action == "schedule":
        if not b.scheduled_at or b.scheduled_at <= timezone.now():
            return _problem("Kelajakdagi vaqtni tanlang")
        b.status = Broadcast.SCHEDULED
    else:
        b.scheduled_at = None
        if not services.audience(b.audience).exists():
            return _problem("Qabul qiluvchilar yo'q")
    b.created_by = request.user
    try:
        with transaction.atomic():
            b.save()
    except IntegrityError:
        existing = get_object_or_404(Broadcast, nonce=b.nonce)
        return JsonResponse({"ok": True, "id": existing.pk, "duplicate": True})
    started = action == "send" and services.start(b.pk)
    return JsonResponse({"ok": True, "id": b.pk, "started": started})


def _test(request, b: Broadcast, photo):
    if not request.user.telegram_id:
        return _problem("Admin akkauntingizga Telegram ulanmagan: saytda Profil → Telegram'ni ulash")
    b.photo = ""  # the uploaded bytes are sent directly, nothing is stored
    data = None
    if photo:
        photo.seek(0)
        data = photo.read()
    out = services.send_test(b, request.user, data)
    if out.status == delivery.SENT:
        return JsonResponse({"ok": True})
    hint = "Avval botga /start yuboring. " if out.status == delivery.BLOCKED else ""
    return _problem(f"Yuborilmadi: {hint}{out.detail}", 502)


@staff_member_required
@require_POST
def act(request, pk: int, action: str):
    b = get_object_or_404(Broadcast, pk=pk)
    if action == "resume":
        if b.status in (Broadcast.DONE, Broadcast.CANCELLED, Broadcast.SCHEDULED):
            return _problem("Bu xabarni davom ettirib bo'lmaydi", 409)
        if not services.start(pk):
            return _problem("Hozir boshqa xabar yuborilmoqda. Biroz kutib qayta bosing.", 409)
    elif action in ("pause", "cancel"):
        if not services.stop(pk, Broadcast.PAUSED if action == "pause" else Broadcast.CANCELLED):
            return _problem("Holat allaqachon o'zgargan", 409)
    else:
        return _problem("action", 404)
    return JsonResponse({"ok": True})
