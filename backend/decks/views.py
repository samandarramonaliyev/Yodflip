from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from gamification.services import award_event

from .models import Card, Deck, WordSet
from .parsing import cards_to_csv, csv_to_cards, parse_bulk
from .serializers import (
    BulkSerializer,
    CardSerializer,
    DeckDetailSerializer,
    DeckSerializer,
    QuickAddSerializer,
    ReorderSerializer,
    WordSetListSerializer,
    WordSetSerializer,
)


def _next_order(deck: Deck) -> int:
    return (deck.cards.aggregate(m=Max("order"))["m"] or 0) + 1


class DeckViewSet(viewsets.ModelViewSet):
    queryset = Deck.objects.none()  # for schema generation; get_queryset() scopes to the owner
    serializer_class = DeckSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Deck.objects.filter(owner=self.request.user).annotate(card_count=Count("cards"))
        track = self.request.query_params.get("track")
        if track in ("en", "de"):
            qs = qs.filter(track=track)
        return qs.select_related("owner")

    def get_serializer_class(self):
        return DeckDetailSerializer if self.action == "retrieve" else DeckSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        award_event(self.request.user, "deck_created")

    @extend_schema(parameters=[OpenApiParameter("track", str)], responses={200: DeckSerializer(many=True)})
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=dict, responses={200: DeckDetailSerializer})
    @action(detail=True, methods=["post"])
    def translate(self, request, pk=None):
        """'AI bilan tarjima qilish': fill extra_translations[lang] for cards that miss it (cached)."""
        from .ai import AIUnavailable, translate_terms

        deck = self.get_object()
        lang = request.data.get("lang")
        if lang not in ("uz", "ru", "en", "de") or lang == deck.track:
            raise ValidationError({"lang": "invalid_language_pair"})
        cards = [
            c for c in deck.cards.all() if lang != deck.translation_lang and not (c.extra_translations or {}).get(lang)
        ]
        if cards:
            try:
                result = translate_terms(
                    deck.track, lang, [(c.term, c.translation, deck.translation_lang) for c in cards]
                )
            except AIUnavailable:
                return Response({"detail": "ai_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            for c, text in zip(cards, result, strict=True):
                if text:
                    c.extra_translations = {**(c.extra_translations or {}), lang: text[:300]}
                    c.save(update_fields=["extra_translations"])
        deck = Deck.objects.annotate(card_count=Count("cards")).get(pk=deck.pk)
        return Response(DeckDetailSerializer(deck, context={"request": request}).data)

    # --- cards -------------------------------------------------------------
    @action(detail=True, methods=["get", "post"], serializer_class=CardSerializer)
    def cards(self, request, pk=None):
        deck = self.get_object()
        if request.method == "GET":
            return Response(CardSerializer(deck.cards.all(), many=True, context={"request": request}).data)
        ser = CardSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save(deck=deck, order=ser.validated_data.get("order") or _next_order(deck))
        deck.save(update_fields=["updated_at"])
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True, methods=["patch", "delete"], url_path=r"cards/(?P<card_id>\d+)", serializer_class=CardSerializer
    )
    def card_detail(self, request, pk=None, card_id=None):
        deck = self.get_object()
        card = get_object_or_404(Card, pk=card_id, deck=deck)
        if request.method == "DELETE":
            card.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        ser = CardSerializer(card, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    @extend_schema(request=BulkSerializer, responses={201: dict})
    @action(detail=True, methods=["post"], serializer_class=BulkSerializer)
    def bulk(self, request, pk=None):
        deck = self.get_object()
        ser = BulkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cards, bad = parse_bulk(ser.validated_data["text"], deck.track)
        start = _next_order(deck)
        Card.objects.bulk_create([Card(deck=deck, order=start + i, **c) for i, c in enumerate(cards)])
        deck.save(update_fields=["updated_at"])
        return Response({"added": len(cards), "bad_lines": bad}, status=status.HTTP_201_CREATED)

    @extend_schema(request=ReorderSerializer, responses={200: dict})
    @action(detail=True, methods=["post"], serializer_class=ReorderSerializer)
    def reorder(self, request, pk=None):
        deck = self.get_object()
        ser = ReorderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["ids"]
        cards = {c.id: c for c in deck.cards.filter(id__in=ids)}
        with transaction.atomic():
            for i, cid in enumerate(ids):
                if cid in cards:
                    cards[cid].order = i
            Card.objects.bulk_update(cards.values(), ["order"])
        return Response({"ok": True})

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        deck = self.get_object()
        resp = HttpResponse(cards_to_csv(deck.cards.all()), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="deck-{deck.id}.csv"'
        return resp

    @extend_schema(
        request={
            "multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}
        },
        responses={201: dict},
    )
    @action(detail=True, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_csv(self, request, pk=None):
        deck = self.get_object()
        f = request.FILES.get("file")
        if not f:
            raise ValidationError({"file": "required"})
        if f.size > 2 * 1024 * 1024:
            raise ValidationError({"file": "too_large"})
        rows = csv_to_cards(f.read().decode("utf-8", errors="replace"))
        start = _next_order(deck)
        Card.objects.bulk_create([Card(deck=deck, order=start + i, **r) for i, r in enumerate(rows)])
        return Response({"added": len(rows)}, status=status.HTTP_201_CREATED)


class QuickAddCardView(APIView):
    """One-tap "add to deck" from any game or list."""

    @extend_schema(request=QuickAddSerializer, responses={201: CardSerializer})
    def post(self, request):
        ser = QuickAddSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        deck = get_object_or_404(Deck, pk=d["deck_id"], owner=request.user)
        if deck.cards.filter(term__iexact=d["term"]).exists():
            return Response({"detail": "duplicate"}, status=status.HTTP_200_OK)
        card = Card.objects.create(
            deck=deck,
            term=d["term"],
            translation=d.get("translation") or "—",
            definition=d.get("definition", ""),
            article=d.get("article", ""),
            order=_next_order(deck),
        )
        deck.save(update_fields=["updated_at"])
        return Response(CardSerializer(card).data, status=status.HTTP_201_CREATED)


class SharedDeckView(APIView):
    """View a shared deck by its link code; POST copies it into the caller's account."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def _get(self, request, code):
        deck = get_object_or_404(Deck.objects.annotate(card_count=Count("cards")), share_code=code)
        is_owner = request.user.is_authenticated and deck.owner_id == request.user.id
        if not deck.is_public and not is_owner:
            from django.http import Http404

            raise Http404
        return deck

    @extend_schema(responses={200: DeckDetailSerializer})
    def get(self, request, code):
        deck = self._get(request, code)
        return Response(DeckDetailSerializer(deck, context={"request": request}).data)

    @extend_schema(request=None, responses={201: DeckSerializer})
    def post(self, request, code):
        src = self._get(request, code)
        with transaction.atomic():
            copy = Deck.objects.create(
                owner=request.user,
                name=src.name,
                track=src.track,
                description=src.description,
                translation_lang=src.translation_lang,
                copied_from=src,
            )
            Card.objects.bulk_create(
                [
                    Card(
                        deck=copy,
                        term=c.term,
                        translation=c.translation,
                        extra_translations=c.extra_translations,
                        definition=c.definition,
                        example=c.example,
                        article=c.article,
                        image=c.image,
                        order=c.order,
                    )
                    for c in src.cards.all()
                ]
            )
        copy.card_count = src.card_count
        return Response(DeckSerializer(copy, context={"request": request}).data, status=status.HTTP_201_CREATED)


class PublicDecksView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter("track", str), OpenApiParameter("q", str)],
        responses={200: DeckSerializer(many=True)},
    )
    def get(self, request):
        qs = Deck.objects.filter(is_public=True).annotate(card_count=Count("cards")).filter(card_count__gt=0)
        track = request.query_params.get("track")
        if track in ("en", "de"):
            qs = qs.filter(track=track)
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return Response(DeckSerializer(qs.select_related("owner")[:50], many=True, context={"request": request}).data)


class WordSetViewSet(viewsets.ModelViewSet):
    queryset = WordSet.objects.none()  # for schema generation; get_queryset() scopes to the owner
    serializer_class = WordSetSerializer

    def get_queryset(self):
        qs = WordSet.objects.filter(owner=self.request.user)
        track = self.request.query_params.get("track")
        if track in ("en", "de"):
            qs = qs.filter(track=track)
        if self.action == "list":
            return qs.annotate(pair_count=Count("pairs"))
        return qs.prefetch_related("pairs")

    def get_serializer_class(self):
        return WordSetListSerializer if self.action == "list" else WordSetSerializer

    @extend_schema(request=None, responses={201: DeckSerializer})
    @action(detail=True, methods=["post"], url_path="to-deck")
    def to_deck(self, request, pk=None):
        ws = self.get_object()
        with transaction.atomic():
            deck = Deck.objects.create(owner=request.user, name=ws.name, track=ws.track, description="")
            Card.objects.bulk_create(
                [
                    Card(
                        deck=deck,
                        term=p.word,
                        translation=p.translation_uz or "—",
                        extra_translations={k: v for k, v in (p.translations or {}).items() if k != ws.track},
                        definition=p.definition,
                        article=p.article,
                        order=i,
                    )
                    for i, p in enumerate(ws.pairs.all())
                ]
            )
        award_event(request.user, "deck_created")
        deck.card_count = ws.pairs.count()
        return Response(DeckSerializer(deck, context={"request": request}).data, status=status.HTTP_201_CREATED)
