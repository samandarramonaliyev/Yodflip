from django.contrib import admin

from .models import DailyChallengeScore


@admin.register(DailyChallengeScore)
class DailyChallengeScoreAdmin(admin.ModelAdmin):
    list_display = ("user", "track", "date", "correct", "duration_ms", "score")
    list_filter = ("track", "date")
    raw_id_fields = ("user",)
