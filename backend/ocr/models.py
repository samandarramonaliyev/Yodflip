from django.conf import settings
from django.db import models


class ScanLog(models.Model):
    """One OCR request (used for the per-user daily rate limit). The image itself is never stored."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scans")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    engine = models.CharField(max_length=20, blank=True)
    pairs_found = models.PositiveIntegerField(default=0)
    ok = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
