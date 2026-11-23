from django.contrib import admin

from .models import Duel, DuelParticipant


class ParticipantInline(admin.TabularInline):
    model = DuelParticipant
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = ("code", "creator", "track", "mode", "source", "status", "winner", "created_at")
    list_filter = ("track", "mode", "status")
    raw_id_fields = ("creator", "winner", "rematch_of")
    inlines = [ParticipantInline]
