from django.contrib import admin

from .models import QuizSession, QuizSettings


@admin.register(QuizSettings)
class QuizSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "hour", "timezone", "questions", "bot_blocked", "last_sent_on")
    list_filter = ("enabled", "bot_blocked")
    raw_id_fields = ("user",)


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = ("sid", "user", "track", "status", "index", "correct", "created_at")
    list_filter = ("status", "track")
    raw_id_fields = ("user",)
