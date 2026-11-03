"""Sign-in, refresh, sign-out, password change and the device-session list.

Routes:

  POST   /api/token/                    sign in; opens a DeviceSession (auth throttle)
  POST   /api/token/refresh/            refresh; refused once the session ends
  POST   /api/auth/logout/              end this device's session
  POST   /api/auth/password/            change password; signs the OTHER devices out
  GET    /api/sessions/                 live sessions, this device first
  DELETE /api/sessions/<uuid>/          end one session (sign that device out)
  POST   /api/sessions/revoke-others/   end every session but this one

Views stay thin (CLAUDE.md); the logic is in models.py and utils/.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .authentication import current_session_id
from .models import DeviceSession
from .serializers import (
    ChangePasswordSerializer,
    SessionTokenObtainPairSerializer,
    SessionTokenRefreshSerializer,
)
from .throttling import AuthRateThrottle
from .utils.sessions import revoke_others, session_overview


class SessionTokenObtainPairView(TokenObtainPairView):
    serializer_class = SessionTokenObtainPairSerializer
    throttle_classes = [AuthRateThrottle]


class SessionTokenRefreshView(TokenRefreshView):
    serializer_class = SessionTokenRefreshSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sid = current_session_id(request)
        if sid:
            DeviceSession.objects.filter(pk=sid, user=request.user).revoke()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    """Change the password, keep this device signed in, sign the others out.

    Store-Arbitrage left existing tokens working after a change. With device
    sessions the usual reason to change a password (someone else may have it)
    can actually be acted on, so every other session ends here.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        signed_out = revoke_others(request.user, current_session_id(request))
        return Response({"detail": "Password updated.", "signed_out": signed_out})


class SessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(session_overview(request.user, current_session_id(request)))


class SessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        session = get_object_or_404(DeviceSession.objects.live(), pk=pk, user=request.user)
        DeviceSession.objects.filter(pk=session.pk).revoke()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevokeOtherSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"revoked": revoke_others(request.user, current_session_id(request))})
