from django.contrib import admin

from .models import SeedState, StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ("name", "content_type", "size", "created_at")
    search_fields = ("name",)
    exclude = ("content",)


@admin.register(SeedState)
class SeedStateAdmin(admin.ModelAdmin):
    list_display = ("key", "digest", "loaded_at")
