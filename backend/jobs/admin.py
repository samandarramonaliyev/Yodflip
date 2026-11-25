from django.contrib import admin

from .models import CronRunLog


@admin.register(CronRunLog)
class CronRunLogAdmin(admin.ModelAdmin):
    list_display = ("job", "trigger", "started_at", "matched", "sent", "failed", "skipped", "error")
    list_filter = ("job", "trigger")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
