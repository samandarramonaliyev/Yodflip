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
    list_display = ("user", "pack", "score", "finished_at", "created_at")
    list_filter = ("pack",)
    raw_id_fields = ("user",)


@admin.register(ExamGoal)
class ExamGoalAdmin(admin.ModelAdmin):
    list_display = ("user", "pack", "per_day")
    raw_id_fields = ("user",)
