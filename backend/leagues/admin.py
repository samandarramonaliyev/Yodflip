from django.contrib import admin

from .models import LeagueGroup, LeagueMember, LeagueTier, LeagueWeek, UserLeague, XpFlag


@admin.register(LeagueTier)
class LeagueTierAdmin(admin.ModelAdmin):
    list_display = ("emoji", "name_uz", "code", "order", "promote", "demote")
    ordering = ("order",)


@admin.register(LeagueWeek)
class LeagueWeekAdmin(admin.ModelAdmin):
    list_display = ("start", "finalized_at")


@admin.register(LeagueGroup)
class LeagueGroupAdmin(admin.ModelAdmin):
    list_display = ("week", "tier", "number", "size")
    list_filter = ("tier",)


@admin.register(LeagueMember)
class LeagueMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "week", "tier", "xp", "rank", "result")
    list_filter = ("tier", "result")
    raw_id_fields = ("user", "group")
    search_fields = ("user__display_name",)


@admin.register(UserLeague)
class UserLeagueAdmin(admin.ModelAdmin):
    list_display = ("user", "tier", "trophies")
    list_filter = ("tier",)
    raw_id_fields = ("user",)


@admin.register(XpFlag)
class XpFlagAdmin(admin.ModelAdmin):
    """Suspicious XP spikes for review."""

    list_display = ("user", "day", "xp", "reason", "reviewed", "created_at")
    list_filter = ("reason", "reviewed")
    list_editable = ("reviewed",)
    raw_id_fields = ("user",)
