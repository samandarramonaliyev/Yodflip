from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    level = serializers.IntegerField(read_only=True)
    has_password = serializers.SerializerMethodField()
    is_telegram_linked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "telegram_id",
            "telegram_username",
            "avatar_url",
            "active_track",
            "cefr_level_en",
            "cefr_level_de",
            "ui_language",
            "xp",
            "level",
            "streak",
            "best_streak",
            "last_active_date",
            "reminder_time",
            "date_joined",
            "has_password",
            "is_telegram_linked",
        )
        read_only_fields = (
            "id",
            "email",
            "telegram_id",
            "telegram_username",
            "xp",
            "streak",
            "best_streak",
            "last_active_date",
            "date_joined",
        )

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()

    def get_is_telegram_linked(self, obj) -> bool:
        return obj.telegram_id is not None


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    display_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    ui_language = serializers.ChoiceField(choices=["uz", "en", "ru"], required=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("email_taken")
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, data):
        return User.objects.create_user(
            email=data["email"],
            password=data["password"],
            display_name=data.get("display_name") or data["email"].split("@")[0],
            ui_language=data.get("ui_language", "uz"),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class SetEmailPasswordSerializer(serializers.Serializer):
    """Lets a Telegram-only account add email+password (linking web login)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_email(self, value):
        value = value.strip().lower()
        user = self.context["request"].user
        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("email_taken")
        return value


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
