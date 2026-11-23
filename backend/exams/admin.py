from django.contrib import admin

from .models import ExamGoal, ExamPack, ExamSimulation, ExamTopic, PackWord


@admin.register(ExamPack)
class ExamPackAdmin(admin.ModelAdmin):
    list_display = ("slug", "track", "name_uz", "order")


@admin.register(ExamTopic)
class ExamTopicAdmin(admin.ModelAdmin):
    list_display = ("pack", "slug", "name_uz", "order")
    list_filter = ("pack",)


@admin.register(PackWord)
class PackWordAdmin(admin.ModelAdmin):
    list_display = ("pack", "topic", "word", "order")
    list_filter = ("pack",)
    search_fields = ("word__word",)
    raw_id_fields = ("word",)


@admin.register(ExamSimulation)
class ExamSimulationAdmin(admin.ModelAdmin):
    list_display = ("user", "pack", "score", "violation_count", "terminated", "finished_at", "created_at")
    list_filter = ("pack", "terminated")
    raw_id_fields = ("user",)

    @admin.display(description="violations")
    def violation_count(self, obj):
        return len(obj.violations)


@admin.register(ExamGoal)
class ExamGoalAdmin(admin.ModelAdmin):
    list_display = ("user", "pack", "per_day")
    raw_id_fields = ("user",)
