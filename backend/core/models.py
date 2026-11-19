from django.db import models


class StoredFile(models.Model):
    """Uploaded media kept in PostgreSQL (Render's container disk is ephemeral)."""

    name = models.CharField(max_length=255, unique=True)
    content = models.BinaryField()
    content_type = models.CharField(max_length=100, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SeedState(models.Model):
    """Remembers which version (hash) of a seed was loaded, so seeding runs only once."""

    key = models.CharField(max_length=50, unique=True)
    digest = models.CharField(max_length=64)
    loaded_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.digest[:10]}"
