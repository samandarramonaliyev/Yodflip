from django.contrib import admin
from django.db.models import Count

from .models import ShareEvent, ShareImage


@admin.register(ShareEvent)
class ShareEventAdmin(admin.ModelAdmin):
    """Share analytics: filter by template / platform; the totals per template are shown above the list."""

    list_display = ("created_at", "template", "platform", "user")
    list_filter = ("template", "platform", "created_at")
    date_hierarchy = "created_at"
    raw_id_fields = ("user",)

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data["cl"].queryset
        except (AttributeError, KeyError):
            return response
        rows = qs.values("template", "platform").annotate(n=Count("id")).order_by("template", "-n")
        summary = ", ".join(f"{r['template']}/{r['platform']}: {r['n']}" for r in rows)
        self.message_user(request, f"Jami: {qs.count()} · {summary}" if summary else "Hali ulashish yo'q")
        return response


@admin.register(ShareImage)
class ShareImageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "file")
    raw_id_fields = ("user",)
