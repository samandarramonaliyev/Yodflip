"""A Django Storage that keeps files in the database (core.StoredFile).

Used for card images so nothing is written to the container's local disk.
Files are served by core.views.media with long cache headers.
"""

from __future__ import annotations

import mimetypes
import posixpath
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DatabaseStorage(Storage):
    def _model(self):
        from .models import StoredFile

        return StoredFile

    def _open(self, name, mode="rb"):
        obj = self._model().objects.get(name=name)
        f = ContentFile(bytes(obj.content), name=name)
        f.content_type = obj.content_type
        return f

    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        ctype = getattr(content, "content_type", None) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._model().objects.create(name=name, content=data, content_type=ctype, size=len(data))
        return name

    def get_available_name(self, name, max_length=None):
        # Unique, unguessable names: <dir>/<uuid>.<ext>
        directory, filename = posixpath.split(name.replace("\\", "/"))
        ext = posixpath.splitext(filename)[1].lower()[:10]
        return posixpath.join(directory, f"{uuid.uuid4().hex}{ext}")

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        return self._model().objects.values_list("size", flat=True).get(name=name)

    def url(self, name):
        from django.conf import settings

        return f"{settings.MEDIA_URL.rstrip('/')}/{name}"
