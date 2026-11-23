from django.contrib import admin

from .models import TtsAudio


@admin.register(TtsAudio)
class TtsAudioAdmin(admin.ModelAdmin):
    list_display = ("text", "lang", "voice", "created_by", "created_at")
    list_filter = ("lang", "voice")
    search_fields = ("text",)
    exclude = ("data",)
    raw_id_fields = ("created_by",)
