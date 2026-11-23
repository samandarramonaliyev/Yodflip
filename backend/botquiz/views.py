from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import QUESTION_CHOICES


class QuizSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    hour = serializers.IntegerField(min_value=0, max_value=23, required=False)
    timezone = serializers.CharField(max_length=50, required=False)
    questions = serializers.ChoiceField(choices=QUESTION_CHOICES, required=False)
    translation_lang = serializers.ChoiceField(choices=["uz", "ru", "en", "de"], required=False, allow_blank=True)
    quiet_days = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), required=False, max_length=7
    )

    def validate_timezone(self, value):
        if not services.valid_timezone(value):
            raise serializers.ValidationError("invalid_timezone")
        return value

    def validate_quiet_days(self, value):
        return sorted(set(value))


class QuizSettingsView(APIView):
    """Daily in-chat quiz settings (also editable with /quiz settings in the bot)."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(services.settings_dict(services.settings_for(request.user)))

    @extend_schema(request=QuizSettingsSerializer, responses={200: dict})
    def patch(self, request):
        ser = QuizSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(services.settings_dict(services.update_settings(request.user, **ser.validated_data)))
