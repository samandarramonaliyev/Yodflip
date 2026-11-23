from django.conf import settings
from django.db import models


class TtsAudio(models.Model):
    """A cached MP3: bytes in PostgreSQL, or the URL of the bucket object."""

    key = models.CharField(max_length=64, unique=True)
    lang = models.CharField(max_length=5)
    voice = models.CharField(max_length=60)
    text = models.CharField(max_length=300)
    data = models.BinaryField(null=True, blank=True)
    url = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tts_audios"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_by", "created_at"])]

    def __str__(self):
        return f"{self.lang}: {self.text}"
