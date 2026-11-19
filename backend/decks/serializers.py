from django.db import transaction
from rest_framework import serializers

from .models import Card, Deck, SetPair, WordSet


class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = ("id", "term", "translation", "definition", "example", "article", "image", "order")
        read_only_fields = ("id",)
        extra_kwargs = {"order": {"required": False}}

    def validate_article(self, value):
        value = (value or "").strip().lower()
        if value and value not in ("der", "die", "das"):
            raise serializers.ValidationError("invalid_article")
        return value


class DeckSerializer(serializers.ModelSerializer):
    card_count = serializers.IntegerField(read_only=True)
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Deck
        fields = (
            "id",
            "name",
            "track",
            "description",
            "is_public",
            "share_code",
            "card_count",
            "owner_name",
            "is_owner",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "share_code", "created_at", "updated_at")

    def get_is_owner(self, obj) -> bool:
        req = self.context.get("request")
        return bool(req and req.user.is_authenticated and obj.owner_id == req.user.id)


class DeckDetailSerializer(DeckSerializer):
    cards = CardSerializer(many=True, read_only=True)

    class Meta(DeckSerializer.Meta):
        fields = DeckSerializer.Meta.fields + ("cards",)


class BulkSerializer(serializers.Serializer):
    text = serializers.CharField()


class ReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField())


class QuickAddSerializer(serializers.Serializer):
    deck_id = serializers.IntegerField()
    term = serializers.CharField(max_length=200)
    translation = serializers.CharField(max_length=300, allow_blank=True, required=False)
    definition = serializers.CharField(max_length=500, allow_blank=True, required=False)
    article = serializers.CharField(max_length=3, allow_blank=True, required=False)


class SetPairSerializer(serializers.ModelSerializer):
    class Meta:
        model = SetPair
        fields = ("id", "word", "definition", "part_of_speech", "article", "translation_uz", "order")
        read_only_fields = ("id",)
        extra_kwargs = {"order": {"required": False}}


class WordSetSerializer(serializers.ModelSerializer):
    pairs = SetPairSerializer(many=True)
    pair_count = serializers.SerializerMethodField()

    class Meta:
        model = WordSet
        fields = ("id", "name", "track", "pairs", "pair_count", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_pair_count(self, obj) -> int:
        return obj.pairs.count()

    def validate_pairs(self, pairs):
        if not pairs:
            raise serializers.ValidationError("at_least_one_pair")
        if len(pairs) > 200:
            raise serializers.ValidationError("too_many_pairs")
        return pairs

    @transaction.atomic
    def create(self, data):
        pairs = data.pop("pairs")
        ws = WordSet.objects.create(owner=self.context["request"].user, **data)
        self._write_pairs(ws, pairs)
        return ws

    @transaction.atomic
    def update(self, ws, data):
        pairs = data.pop("pairs", None)
        for k, v in data.items():
            setattr(ws, k, v)
        ws.save()
        if pairs is not None:
            ws.pairs.all().delete()
            self._write_pairs(ws, pairs)
        return ws

    @staticmethod
    def _write_pairs(ws, pairs):
        SetPair.objects.bulk_create(
            [SetPair(word_set=ws, order=i, **{k: v for k, v in p.items() if k != "order"}) for i, p in enumerate(pairs)]
        )


class WordSetListSerializer(serializers.ModelSerializer):
    pair_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = WordSet
        fields = ("id", "name", "track", "pair_count", "created_at")
