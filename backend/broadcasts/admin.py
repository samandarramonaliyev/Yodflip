from django.contrib import admin
from django.shortcuts import redirect

from .models import Broadcast


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    """Only the menu entry: the page itself is /admin/broadcast/."""

    def changelist_view(self, request, extra_context=None):
        return redirect("broadcast")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff
