from django.contrib import admin

from .models import LevelCompletion, LevelRound, Pack, UserLevelWord, UserWord, Word


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ("id", "track", "level", "slug", "name_en", "emoji", "order")
    list_filter = ("track", "level")


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("id", "track", "level", "article", "word", "translation_uz", "part_of_speech", "pack")
    list_filter = ("track", "level", "part_of_speech", "pack")
    search_fields = ("word", "translation_uz", "definition")


@admin.register(UserWord)
class UserWordAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "track", "term", "box", "correct_count", "miss_count", "want_to_learn")
    list_filter = ("track", "box", "want_to_learn")
    search_fields = ("term", "user__email")
    raw_id_fields = ("user", "word")


@admin.register(UserLevelWord)
class UserLevelWordAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "track", "level", "word", "found_at", "filler_uses", "last_shown_at")
    list_filter = ("track", "level")
    search_fields = ("word__word", "user__email")
    raw_id_fields = ("user", "word", "found_round")


@admin.register(LevelRound)
class LevelRoundAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "track", "level", "game", "xp_awarded", "created_at")
    list_filter = ("track", "level", "game")
    raw_id_fields = ("user",)


@admin.register(LevelCompletion)
class LevelCompletionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "track", "level", "bonus_xp", "created_at")
    raw_id_fields = ("user",)
