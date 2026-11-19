from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)
    list_display = ("id", "email", "display_name", "telegram_id", "active_track", "xp", "streak")
    search_fields = ("email", "display_name", "telegram_username")
    list_filter = ("active_track", "is_staff")
    fieldsets = (
        (None, {"fields": ("email", "password", "display_name")}),
        ("Telegram", {"fields": ("telegram_id", "telegram_username", "avatar_url")}),
        (
            "Learning",
            {
                "fields": (
                    "active_track",
                    "cefr_level_en",
                    "cefr_level_de",
                    "ui_language",
                    "xp",
                    "streak",
                    "best_streak",
                    "last_active_date",
                    "reminder_time",
                )
            },
        ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
