import random

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import TRACK_CHOICES
from gamification.models import GameSession
from gamification.services import check_achievements, level_for_xp, record_activity, today
from words.levels import record_answers, round_progress
from words.models import LevelRound, UserLevelWord
from words.services import apply_answer, record_answer
from words.translations import resolve

from .models import DailyChallengeScore
from .rules import GAMES, SESSION_XP_CAP, XP_PER_CORRECT, allowed_for_track, mode_for
from .scoring import daily_score, match_round_score, session_xp
from .sources import get_items


class ResultItemSerializer(serializers.Serializer):
    term = serializers.CharField(max_length=200)
    word_id = serializers.IntegerField(required=False, allow_null=True)
    translation = serializers.CharField(max_length=300, required=False, allow_blank=True)
    definition = serializers.CharField(max_length=500, required=False, allow_blank=True)
    article = serializers.CharField(max_length=3, required=False, allow_blank=True)
    correct = serializers.BooleanField()


class ResultsSerializer(serializers.Serializer):
    game = serializers.ChoiceField(choices=list(GAMES))
    track = serializers.ChoiceField(choices=TRACK_CHOICES)
    source = serializers.CharField(max_length=40, required=False, allow_blank=True)
    results = ResultItemSerializer(many=True)
    duration_ms = serializers.IntegerField(min_value=0, required=False, default=0)
    combo_max = serializers.IntegerField(min_value=0, required=False, default=0)
    session_id = serializers.CharField(max_length=40, required=False, allow_blank=True)
    translation_lang = serializers.CharField(max_length=2, required=False, allow_blank=True)
    assignment_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs.get("source") in ("level", "exam") and not attrs.get("session_id"):
            raise serializers.ValidationError({"session_id": "required_for_level"})
        return attrs

    def validate_results(self, value):
        if len(value) > 300:
            raise serializers.ValidationError("too_many_results")
        return value


class WordsView(APIView):
    """Items for a game. Content side is chosen by the Game Direction Rules."""

    @extend_schema(
        parameters=[
            OpenApiParameter("game", str, enum=list(GAMES)),
            OpenApiParameter("track", str, enum=["en", "de"]),
            OpenApiParameter(
                "source",
                str,
                enum=[
                    "level",
                    "levelreview",
                    "deck",
                    "set",
                    "missed",
                    "want",
                    "learned",
                    "review",
                    "daily",
                    "examreview",
                    "lesson",
                    "assignment",
                ],
            ),
            OpenApiParameter("level", str),
            OpenApiParameter("pack", str),
            OpenApiParameter("id", int),
            OpenApiParameter("limit", int),
            OpenApiParameter("translation_lang", str, enum=["uz", "ru", "en", "de"]),
            OpenApiParameter("direction", str, enum=["forward", "reverse"]),
        ],
        responses={200: dict},
    )
    def get(self, request):
        p = request.query_params
        game = p.get("game", "match")
        track = p.get("track") or request.user.active_track
        if game not in GAMES or track not in ("en", "de"):
            raise ValidationError({"detail": "invalid_game_or_track"})
        if not allowed_for_track(game, track):
            raise ValidationError({"detail": "game_not_available_for_track"})
        mode = mode_for(game)
        lang, direction = resolve(track, p.get("translation_lang"), p.get("direction"))
        source = p.get("source", "level")
        if source == "deck":
            from decks.models import Deck

            deck = Deck.objects.filter(pk=p.get("id")).only("translation_lang").first()
            lang = deck.translation_lang if deck else lang  # a deck always plays in its own language
        items = get_items(request.user, track, source, p, mode, translation_lang=lang)
        if p.get("source") not in ("daily", "assignment"):  # assignment: unlearned words first
            random.shuffle(items)
        try:
            limit = max(1, min(int(p.get("limit", 200)), 200))
        except ValueError:
            limit = 200
        items = items[:limit]
        payload = {
            "game": game,
            "track": track,
            "mode": mode,
            "translation_lang": lang,
            "direction": direction,
            "items": items,
        }
        if p.get("source") == "daily":
            done = DailyChallengeScore.objects.filter(user=request.user, track=track, date=today()).first()
            payload["already_played"] = bool(done)
            payload["my_score"] = done.score if done else None
        return Response(payload)


class ResultsView(APIView):
    """Submit a finished game: updates Leitner boxes, XP, streak, achievements."""

    @extend_schema(request=ResultsSerializer, responses={200: dict})
    def post(self, request):
        ser = ResultsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        user = request.user
        game, track = d["game"], d["track"]
        if not allowed_for_track(game, track):
            raise ValidationError({"detail": "game_not_available_for_track"})
        results = d["results"]
        lang = ""
        if d.get("translation_lang"):
            lang, _ = resolve(track, d["translation_lang"])
            if lang != "uz":
                # UserWord.translation_uz only stores Uzbek: never copy RU / EN / DE text into it.
                results = [{**r, "translation": ""} for r in results]
        attempts = len(results)
        correct = sum(1 for r in results if r["correct"])
        learned_now = []
        level_payload = None
        assignment = None
        if d.get("assignment_id"):
            from classes.services import assignment_for_player

            assignment = assignment_for_player(user, d["assignment_id"])
        with transaction.atomic():
            if d.get("source") in ("level", "exam"):
                xp, perfect, level_payload = self._level_round(user, d, results, game, correct, attempts)
                learned_now = level_payload.pop("learned_terms")
            elif game == "flashcards":
                # Lists were already updated card by card via /api/words/flash/answer/.
                xp, perfect = session_xp(game, correct, attempts, 0)
            elif d.get("source") in ("examreview", "lesson", "assignment"):
                for r in results:
                    if apply_answer(user, track, r, r["correct"]):
                        learned_now.append(r["term"])
                user.refresh_from_db()  # a finished level may have given bonus XP
                xp, perfect = session_xp(game, correct, attempts, d.get("combo_max", 0))
            else:
                for r in results:
                    uw, became = record_answer(user, track, r, r["correct"])
                    if became:
                        learned_now.append(uw.term)
                xp, perfect = session_xp(game, correct, attempts, d.get("combo_max", 0))
            daily_payload = None
            if game == "daily":
                score = daily_score(correct, d["duration_ms"])
                obj, created = DailyChallengeScore.objects.get_or_create(
                    user=user,
                    track=track,
                    date=today(),
                    defaults={"correct": correct, "duration_ms": d["duration_ms"], "score": score},
                )
                if not created:
                    xp = 0  # replays of the daily challenge don't give XP
                daily_payload = {"score": obj.score, "first_attempt": created}
            GameSession.objects.create(
                user=user,
                track=track,
                game=game,
                mode=GAMES[game],
                source=d.get("source", ""),
                translation_lang=lang if GAMES[game] != "definition" else "",
                xp=xp,
                correct=correct,
                attempts=attempts,
                duration_ms=d["duration_ms"],
                assignment=assignment,
            )
            record_activity(user, xp, correct, attempts)
            new_achievements = check_achievements(user, perfect=perfect, daily=game == "daily")
        resp = {
            "xp_earned": xp,
            "xp_total": user.xp,
            "level": level_for_xp(user.xp),
            "streak": user.streak,
            "correct": correct,
            "attempts": attempts,
            "accuracy": round(100 * correct / attempts) if attempts else 0,
            "perfect": perfect,
            "learned_now": learned_now,
            "new_achievements": new_achievements,
        }
        if game == "match":
            r = match_round_score(correct, attempts - correct)
            resp["flips"] = r.flips
        if daily_payload:
            resp["daily"] = daily_payload
        if level_payload:
            resp["level_round"] = level_payload
        return Response(resp, status=status.HTTP_200_OK)

    @staticmethod
    def _level_round(user, d, results, game, correct, attempts):
        """Level games: XP only for words found for the first time in this round (once per round)."""
        rnd = get_object_or_404(LevelRound, session_id=d["session_id"], user=user)
        answers = [(r["word_id"], r["correct"]) for r in results if r.get("word_id")]
        if game == "flashcards":
            answers = []  # applied by the flash endpoint ("Topa olmadim" must not go to Missed)
        outcome = record_answers(user, rnd, answers) if answers else None
        found_qs = UserLevelWord.objects.filter(found_round=rnd).select_related("word")
        new_found = found_qs.count()
        perfect = correct >= 4 and correct == attempts
        xp = 0
        if LevelRound.objects.filter(pk=rnd.pk, xp_awarded=False).update(xp_awarded=True):
            base = XP_PER_CORRECT.get(game, 5) * new_found
            bonus = (base // 2 if game == "match" else round(base * 0.2)) if perfect else 0
            xp = min(SESSION_XP_CAP, base + bonus)
        payload = {
            "session_id": rnd.session_id,
            "new_found_count": new_found,
            "progress": outcome["progress"] if outcome else round_progress(user, rnd),
            "completed_now": bool(outcome and outcome["completed_now"]),
            "bonus_xp": outcome["bonus_xp"] if outcome else 0,
            "learned_terms": [u.word.display for u in found_qs],
        }
        return xp, perfect, payload


class DailyLeaderboardView(APIView):
    @extend_schema(parameters=[OpenApiParameter("track", str, enum=["en", "de"])], responses={200: dict})
    def get(self, request):
        track = request.query_params.get("track") or request.user.active_track
        rows = DailyChallengeScore.objects.filter(track=track, date=today()).select_related("user")[:100]
        entries = [
            {
                "rank": i + 1,
                "name": r.user.display_name,
                "avatar_url": r.user.avatar_url,
                "telegram_username": r.user.telegram_username,
                "is_telegram": r.user.telegram_id is not None,
                "score": r.score,
                "correct": r.correct,
                "duration_ms": r.duration_ms,
                "is_me": r.user_id == request.user.id,
            }
            for i, r in enumerate(rows)
        ]
        return Response({"track": track, "date": today().isoformat(), "entries": entries})
