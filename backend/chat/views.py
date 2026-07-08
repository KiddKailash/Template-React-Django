"""Chat REST endpoints.

`send` is synchronous: the LLM tool loop blocks the request. The
frontend (if any) should render a pending state until the response
arrives.

Per-user thread scoping: every message is filtered by `request.user`,
so a user only ever sees their own messages. The thread is scoped to
today (UTC) — each morning starts a fresh conversation. Remove the
`date` filter if you want a rolling thread instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from .models import ChatMessage
from .utils.engine import answer

MAX_MESSAGE_CHARS = 4000


def _today():
    return datetime.now(tz=UTC).date()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def today_thread(request: Request) -> Response:
    today = _today()
    messages = ChatMessage.objects.filter(user=request.user, date=today).order_by("created_at")
    return Response(
        {
            "date": today.isoformat(),
            "messages": [
                {
                    "id": m.pk,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send(request: Request) -> Response:
    content = (request.data.get("message") or "").strip()
    if not content:
        return Response({"detail": "message is required"}, status=400)
    if len(content) > MAX_MESSAGE_CHARS:
        return Response({"detail": f"message too long (max {MAX_MESSAGE_CHARS} chars)"}, status=400)

    result = answer(user=request.user, question=content)
    return Response(
        {
            "user_message": {
                "id": result.user_message.pk,
                "role": result.user_message.role,
                "content": result.user_message.content,
                "created_at": result.user_message.created_at.isoformat(),
            },
            "assistant_message": {
                "id": result.assistant_message.pk,
                "role": result.assistant_message.role,
                "content": result.assistant_message.content,
                "created_at": result.assistant_message.created_at.isoformat(),
            },
            "cost_capped": result.cost_capped,
        }
    )
