import uuid

from django.conf import settings
from django.db import models

AUDIENCES = [
    ("all", "Barcha foydalanuvchilar"),
    ("en", "Faqat ingliz tili"),
    ("de", "Faqat nemis tili"),
    ("active7", "So'nggi 7 kunda faol"),
    ("inactive3", "3+ kun faol emas"),
    ("not_today", "Bugun o'ynamagan"),
    ("web", "Saytdan ro'yxatdan o'tgan va Telegram ulangan"),
]
# Not offered in the admin form: used by teacher announcements (audience_ref = the class id).
ALL_AUDIENCES = [*AUDIENCES, ("class", "Sinf o'quvchilari")]


class Broadcast(models.Model):
    QUEUED, SCHEDULED, RUNNING = "queued", "scheduled", "running"
    PAUSED, DONE, CANCELLED = "paused", "done", "cancelled"
    STATUSES = [
        (QUEUED, "Navbatda"),
        (SCHEDULED, "Rejalashtirilgan"),
        (RUNNING, "Yuborilmoqda"),
        (PAUSED, "To'xtatilgan"),
        (DONE, "Tugadi"),
        (CANCELLED, "Bekor qilingan"),
    ]
    BUTTONS = [("", "Tugmasiz"), ("webapp", "Mini App tugmasi"), ("url", "Havola tugmasi")]

    text = models.TextField()
    photo = models.FileField(upload_to="broadcasts", blank=True)
    photo_file_id = models.CharField(max_length=255, blank=True)  # Telegram's id after the first upload
    button_kind = models.CharField(max_length=6, choices=BUTTONS, blank=True)
    button_text = models.CharField(max_length=64, blank=True)
    button_url = models.URLField(max_length=500, blank=True)
    audience = models.CharField(max_length=12, choices=ALL_AUDIENCES, default="all")
    audience_ref = models.CharField(max_length=40, blank=True)  # e.g. the class id for audience="class"
    webapp_path = models.CharField(max_length=200, default="/")  # where the Mini App button opens
    # One value per opened form: a double click or a retried request creates one broadcast.
    nonce = models.UUIDField(unique=True, default=uuid.uuid4)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=QUEUED)
    prepared = models.BooleanField(default=False)  # the recipients were written down, exactly once
    runner = models.CharField(max_length=32, blank=True)  # lock token of the running thread
    total = models.PositiveIntegerField(default=0)
    sent = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "broadcast"
        verbose_name_plural = "📣 Xabar yuborish"

    def __str__(self):
        return f"#{self.pk} {self.status} {self.sent}/{self.total}"


class BroadcastDelivery(models.Model):
    PENDING, SENDING, SENT, FAILED, BLOCKED = "pending", "sending", "sent", "failed", "blocked"
    STATUSES = [(s, s) for s in ("pending", "sending", "sent", "failed", "blocked")]

    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=8, choices=STATUSES, default=PENDING)
    error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["broadcast", "user"], name="uniq_broadcast_user")]
        indexes = [models.Index(fields=["broadcast", "status"], name="broadcast_status")]

    def __str__(self):
        return f"{self.broadcast_id} → {self.user_id} ({self.status})"
