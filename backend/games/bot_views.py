"""Internal endpoints for the Telegram bot (protected by the X-Bot-Secret header)."""

import hmac
from datetime import datetime

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from gamification.services import level_for_xp, today
from words.services import due_queryset

from .sources import daily_words


class BotSecretPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        given = request.headers.get("X-Bot-Secret", "")
        return bool(settings.BOT_API_SECRET) and hmac.compare_digest(given, settings.BOT_API_SECRET)


class BotView(APIView):
    authentication_classes: list = []
    permission_classes = [BotSecretPermission]


def _user(tg_id: int) -> User | None:
    return User.objects.filter(telegram_id=tg_id).first()


class BotStatsView(BotView):
    @extend_schema(responses={200: dict})
    def get(self, request, tg_id: int):
        u = _user(tg_id)
        if not u:
            return Response({"registered": False})
        out = {
            "registered": True,
            "name": u.display_name,
            "xp": u.xp,
            "level": level_for_xp(u.xp),
            "streak": u.streak,
            "played_today": u.last_active_date == today(),
            "ui_language": u.ui_language,
            "tracks": {},
        }
        for track in ("en", "de"):
            qs = u.words.filter(track=track)
            out["tracks"][track] = {
                "learned": qs.filter(box__gte=5).count(),
                "total": qs.filter(seen=True).count(),
                "due": due_queryset(u, track).count(),
            }
        return Response(out)


class BotDailyView(BotView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(
            {
                track: [{"term": w.display, "translation": w.translation_uz} for w in daily_words(track, today())]
                for track in ("en", "de")
            }
        )


class ReminderSerializer(serializers.Serializer):
    reminder_time = serializers.CharField(allow_blank=True, allow_null=True)


class BotReminderSetView(BotView):
    @extend_schema(request=ReminderSerializer, responses={200: dict})
    def post(self, request, tg_id: int):
        u = _user(tg_id)
        if not u:
            return Response({"ok": False, "detail": "not_registered"}, status=404)
        raw = (request.data.get("reminder_time") or "").strip()
        if not raw or raw.lower() == "off":
            u.reminder_time = None
        else:
            try:
                u.reminder_time = datetime.strptime(raw, "%H:%M").time()
            except ValueError:
                return Response({"ok": False, "detail": "bad_time"}, status=400)
        u.save(update_fields=["reminder_time"])
        return Response({"ok": True, "reminder_time": u.reminder_time.strftime("%H:%M") if u.reminder_time else None})


class BotRemindersDueView(BotView):
    """Users whose reminder time has passed today, who haven't played and weren't reminded yet.

    Calling with ?mark=1 marks them as reminded for today.
    """

    @extend_schema(responses={200: dict})
    def get(self, request):
        now = timezone.localtime()
        day = now.date()
        qs = (
            User.objects.filter(telegram_id__isnull=False, reminder_time__isnull=False, reminder_time__lte=now.time())
            .exclude(last_active_date=day)
            .exclude(last_reminder_date=day)
        )
        users = list(qs[:500])
        if request.query_params.get("mark"):
            User.objects.filter(pk__in=[u.pk for u in users]).update(last_reminder_date=day)
        return Response(
            [
                {
                    "telegram_id": u.telegram_id,
                    "name": u.display_name,
                    "streak": u.streak,
                    "ui_language": u.ui_language,
                    "due": due_queryset(u, u.active_track).count(),
                }
                for u in users
            ]
        )
