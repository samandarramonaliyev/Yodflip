from rest_framework import serializers

from accounts.models import TRACK_CHOICES

from .models import Pack, UserWord, Word


class WordSerializer(serializers.ModelSerializer):
    display = serializers.CharField(read_only=True)
    pack_slug = serializers.CharField(source="pack.slug", read_only=True)

    class Meta:
        model = Word
        fields = (
            "id",
            "track",
            "level",
            "pack_slug",
            "word",
            "article",
            "display",
            "part_of_speech",
            "definition",
            "translation_uz",
            "example",
            "example_uz",
        )


class PackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pack
        fields = ("id", "track", "level", "slug", "name_uz", "name_en", "name_ru", "emoji")


class UserWordSerializer(serializers.ModelSerializer):
    is_learned = serializers.BooleanField(read_only=True)
    is_missed = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserWord
        fields = (
            "id",
            "track",
            "term",
            "article",
            "translation_uz",
            "definition",
            "box",
            "correct_count",
            "miss_count",
            "want_to_learn",
            "due_at",
            "last_seen_at",
            "is_learned",
            "is_missed",
        )
        read_only_fields = fields


class WantSerializer(serializers.Serializer):
    track = serializers.ChoiceField(choices=TRACK_CHOICES)
    term = serializers.CharField(max_length=200)
    translation_uz = serializers.CharField(max_length=300, required=False, allow_blank=True)
    definition = serializers.CharField(max_length=500, required=False, allow_blank=True)
    article = serializers.CharField(max_length=3, required=False, allow_blank=True)
    word_id = serializers.IntegerField(required=False, allow_null=True)


class MoveSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=["learned", "missed", "want"])
