from __future__ import annotations

from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenObtainSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import SESSION_CLAIM
from .models import DeviceSession
from .utils.devices import client_ip, describe, user_agent_of


class SessionTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Sign in: check credentials, open a DeviceSession, bind the tokens to it."""

    def validate(self, attrs):
        # Credentials only (sets self.user); the pair is built below so the
        # session id can be put in it before it is signed.
        data = TokenObtainSerializer.validate(self, attrs)
        request = self.context.get("request")
        session = DeviceSession.start(
            self.user,
            user_agent=user_agent_of(request),
            ip_address=client_ip(request),
        )
        refresh = self.get_token(self.user)
        refresh[SESSION_CLAIM] = str(session.pk)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        return data


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh only while the session is live, and extend it when it is."""

    def validate(self, attrs):
        try:
            token = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        sid = token.get(SESSION_CLAIM)
        session = (
            DeviceSession.objects.live()
            .filter(pk=sid, user_id=token.get(api_settings.USER_ID_CLAIM))
            .first()
            if sid
            else None
        )
        if session is None:
            raise InvalidToken("This device was signed out.")

        data = super().validate(attrs)
        session.touch(ip_address=client_ip(self.context.get("request")), extend=True)
        return data


class DeviceSessionSerializer(serializers.ModelSerializer):
    """A session as Settings lists it. ``current_id`` comes in through context."""

    device = serializers.SerializerMethodField()
    current = serializers.SerializerMethodField()

    class Meta:
        model = DeviceSession
        fields = ["id", "device", "ip_address", "created_at", "last_seen_at", "current"]

    def get_device(self, obj) -> dict:
        return describe(obj.user_agent)

    def get_current(self, obj) -> bool:
        return str(obj.pk) == self.context.get("current_id")


class ChangePasswordSerializer(serializers.Serializer):
    """From Store-Arbitrage. The view also signs the user's other devices out."""

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        validate_password(value, user=self.context["request"].user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
