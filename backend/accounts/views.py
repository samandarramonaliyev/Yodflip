from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
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
