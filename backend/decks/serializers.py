from django.db import transaction
from rest_framework import serializers

from words.models import TRANSLATION_LANGS
from words.translations import available_langs

from .models import Card, Deck, SetPair, WordSet


def clean_translations(value) -> dict:
    """{lang: text} with known language codes and short, trimmed texts."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("must_be_object")
    out = {}
    for lang, text in value.items():
        if lang not in TRANSLATION_LANGS:
            raise serializers.ValidationError("invalid_language")
        text = " ".join(str(text or "").split())[:300]
        if text:
            out[lang] = text
    return out


class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = (
            "id",
            "term",
            "translation",
            "extra_translations",
            "definition",
            "example",
            "article",
            "image",
            "order",
            "study_status",
        )
        read_only_fields = ("id", "study_status")
        extra_kwargs = {"order": {"required": False}, "extra_translations": {"required": False}}

    def validate_extra_translations(self, value):
        return clean_translations(value)

    def validate_image(self, image):
        """Re-encode card images (JPEG, max 800px, EXIF stripped) and cap the size."""
        if not image:
            return image
        import io

        from django.conf import settings
        from django.core.files.uploadedfile import InMemoryUploadedFile
        from PIL import Image, ImageOps

        if image.size > settings.MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("image_too_large")
        try:
            img = ImageOps.exif_transpose(Image.open(image)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError("not_an_image") from exc
        img.thumbnail((800, 800))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=82)
        if out.tell() > settings.MAX_CARD_IMAGE_BYTES:
            raise serializers.ValidationError("image_too_large")
        out.seek(0)
        return InMemoryUploadedFile(out, "image", "card.jpg", "image/jpeg", out.getbuffer().nbytes, None)

    def validate_article(self, value):
        value = (value or "").strip().lower()
        if value and value not in ("der", "die", "das"):
            raise serializers.ValidationError("invalid_article")
        return value


class DeckSerializer(serializers.ModelSerializer):
    card_count = serializers.IntegerField(read_only=True)
    owner_name = serializers.CharField(source="owner.display_name", read_only=True)
    is_owner = serializers.SerializerMethodField()
    known_count = serializers.SerializerMethodField()
    learning_count = serializers.SerializerMethodField()

    class Meta:
        model = Deck
        fields = (
            "id",
            "name",
            "track",
            "description",
            "translation_lang",
            "is_public",
            "share_code",
            "card_count",
            "known_count",
            "learning_count",
            "owner_name",
            "is_owner",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "share_code", "created_at", "updated_at")

    def validate(self, attrs):
        track = attrs.get("track") or getattr(self.instance, "track", None)
        lang = attrs.get("translation_lang") or getattr(self.instance, "translation_lang", "uz")
        if lang not in TRANSLATION_LANGS or lang == track:
            raise serializers.ValidationError({"translation_lang": "invalid_language_pair"})
        return attrs

    def get_known_count(self, obj) -> int:
        return obj.cards.filter(study_status="known").count()

    def get_learning_count(self, obj) -> int:
        return obj.cards.filter(study_status="learning").count()

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
        fields = ("id", "word", "definition", "part_of_speech", "article", "translation_uz", "translations", "order")
        read_only_fields = ("id",)
        extra_kwargs = {"order": {"required": False}, "translations": {"required": False}}

    def validate_translations(self, value):
        return clean_translations(value)


class WordSetSerializer(serializers.ModelSerializer):
    pairs = SetPairSerializer(many=True)
    pair_count = serializers.SerializerMethodField()
    available_langs = serializers.SerializerMethodField()

    class Meta:
        model = WordSet
        fields = ("id", "name", "track", "pairs", "pair_count", "available_langs", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_available_langs(self, obj) -> list[str]:
        """Translation languages this set has (others are greyed out in the picker)."""
        return available_langs(obj.track, [{"uz": p.translation_uz, **(p.translations or {})} for p in obj.pairs.all()])

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
