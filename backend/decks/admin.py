from django.contrib import admin

from .models import Card, Deck, SetPair, WordSet


class CardInline(admin.TabularInline):
    model = Card
    extra = 0


class SetPairInline(admin.TabularInline):
    model = SetPair
    extra = 0


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "track", "owner", "is_public", "updated_at")
    list_filter = ("track", "is_public")
    search_fields = ("name", "owner__email")
    raw_id_fields = ("owner", "copied_from")
    inlines = [CardInline]


@admin.register(WordSet)
class WordSetAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "track", "owner", "created_at")
    list_filter = ("track",)
    search_fields = ("name", "owner__email")
    raw_id_fields = ("owner",)
    inlines = [SetPairInline]
