from django.contrib import admin

from .models import DailyActivity, GameSession, UserAchievement


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "track", "game", "mode", "xp", "correct", "attempts", "created_at")
    list_filter = ("track", "game", "mode")
    raw_id_fields = ("user",)


@admin.register(DailyActivity)
class DailyActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "xp", "correct", "attempts", "games")
    raw_id_fields = ("user",)


@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "created_at")
    list_filter = ("code",)
    raw_id_fields = ("user",)
