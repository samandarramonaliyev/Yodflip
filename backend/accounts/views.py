from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TranslationPreference, User
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    SetEmailPasswordSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from .services import tokens_for


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses={201: TokenPairSerializer})
    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        return Response(tokens_for(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=LoginSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authenticate(request, email=ser.validated_data["email"].lower(), password=ser.validated_data["password"])
        if not user:
            return Response({"detail": "invalid_credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(tokens_for(user))


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self) -> User:
        return self.request.user


class SetEmailPasswordView(APIView):
    @extend_schema(request=SetEmailPasswordSerializer, responses={200: UserSerializer})
    def post(self, request):
        ser = SetEmailPasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        user = request.user
        user.email = ser.validated_data["email"]
        user.set_password(ser.validated_data["password"])
        user.save()
        return Response(UserSerializer(user).data)


class TranslationPrefSerializer(serializers.Serializer):
    track = serializers.ChoiceField(choices=["en", "de"])
    preferred_translation_lang = serializers.ChoiceField(choices=["uz", "ru", "en", "de"])
    preferred_direction = serializers.ChoiceField(choices=["forward", "reverse"], default="forward")
    remember_choice = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs["preferred_translation_lang"] == attrs["track"]:
            raise serializers.ValidationError({"preferred_translation_lang": "invalid_language_pair"})
        return attrs


def _pref_dict(user, track: str) -> dict:
    p = TranslationPreference.objects.filter(user=user, track=track).first()
    return {
        "track": track,
        "preferred_translation_lang": p.preferred_translation_lang if p else "uz",
        "preferred_direction": p.preferred_direction if p else "forward",
        "remember_choice": p.remember_choice if p else False,
    }


class TranslationPrefView(APIView):
    """Translation language + direction per track, shared by the website and the Mini App."""

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response({t: _pref_dict(request.user, t) for t in ("en", "de")})

    @extend_schema(request=TranslationPrefSerializer, responses={200: dict})
    def put(self, request):
        ser = TranslationPrefSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = dict(ser.validated_data)
        track = d.pop("track")
        TranslationPreference.objects.update_or_create(user=request.user, track=track, defaults=d)
        return Response(_pref_dict(request.user, track))
