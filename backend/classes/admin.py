from django.contrib import admin

from .models import Announcement, Assignment, Classroom, CoTeacher, Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "max_classes", "max_students", "created_at")
    filter_horizontal = ("admins", "teachers")
    search_fields = ("name",)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    raw_id_fields = ("user",)


class CoTeacherInline(admin.TabularInline):
    model = CoTeacher
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "org", "track", "join_code", "plan", "archived", "created_at")
    list_filter = ("track", "plan", "archived", "org")
    search_fields = ("name", "join_code")
    raw_id_fields = ("owner",)
    inlines = [CoTeacherInline, MembershipInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "classroom", "kind", "target_kind", "target_value", "starts_on", "due_at")
    list_filter = ("kind", "target_kind")
    raw_id_fields = ("classroom", "created_by", "deck")
    exclude = ("word_ids",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("classroom", "author", "created_at")
    raw_id_fields = ("classroom", "author", "broadcast")
