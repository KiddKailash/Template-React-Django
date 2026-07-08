"""HTTP handlers.

Convention (CLAUDE.md): views stay thin — orchestrate, delegate to
`core/utils/` for business logic.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import UserSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def health(_request: Request) -> Response:
    """Liveness/readiness probe. Public."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request: Request) -> Response:
    """Return the currently authenticated user."""
    return Response(UserSerializer(request.user).data)
