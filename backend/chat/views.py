"""Chat REST endpoints.

  GET  /api/chat/today/    today's thread
  POST /api/chat/stream/   send a message; the turn streams back as SSE (the default)
  POST /api/chat/          the same turn as one JSON response (the fallback)

Streaming is the default because a turn can take minutes (several model
calls and tools), and nginx (60 s) and Cloudflare (~100 s) cut off a request
that says nothing for that long: the user got an error while the server kept
working and paying. The stream says something at least every 15 s and shows
which tool is running. Its `done` frame is exactly the JSON endpoint's body.
See `llm/utils/sse.py`.

Per-user thread scoping: every message is filtered by `request.user`. The
thread is scoped to today (UTC); each morning starts a fresh conversation.
Remove the `date` filter if you want a rolling thread instead.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from llm.utils.cost_cap import CostCapExceededError, precheck_only
from llm.utils.sse import SSEAcceptMixin, single_frame_stream, stream_turn, user_message_for

from .models import ChatMessage
from .utils.engine import (
    AnswerResult,
    capped_reply,
    fail_turn,
    finish_turn,
    run_turn,
    start_turn,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000


def _today():
    return datetime.now(tz=UTC).date()


def _message_dict(m: ChatMessage) -> dict:
    return {
        "id": m.pk,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at.isoformat(),
    }


def _answer_body(result: AnswerResult) -> dict:
    """The JSON endpoint's body, and the stream's `done` frame."""
    return {
        "user_message": _message_dict(result.user_message),
        "assistant_message": _message_dict(result.assistant_message),
        "cost_capped": result.cost_capped,
    }


def _validate(request: Request) -> tuple[str | None, Response | None]:
    """The question, or an early JSON rejection (shared by both endpoints)."""
    content = (request.data.get("message") or "").strip()
    if not content:
        return None, Response({"detail": "message is required"}, status=400)
    if len(content) > MAX_MESSAGE_CHARS:
        return None, Response(
            {"detail": f"message too long (max {MAX_MESSAGE_CHARS} chars)"}, status=400
        )
    if not settings.OPENROUTER_API_KEY:
        return None, Response({"detail": "The assistant is not configured."}, status=503)
    return content, None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def today_thread(request: Request) -> Response:
    today = _today()
    messages = ChatMessage.objects.filter(user=request.user, date=today).order_by("created_at")
    return Response({"date": today.isoformat(), "messages": [_message_dict(m) for m in messages]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send(request: Request) -> Response:
    """One turn as a single JSON response. The fallback: prefer stream/."""
    question, rejection = _validate(request)
    if rejection:
        return rejection
    ctx = start_turn(user=request.user, question=question)
    try:
        precheck_only()
    except CostCapExceededError as exc:
        return Response(_answer_body(capped_reply(ctx, exc)))
    try:
        outcome = run_turn(ctx)
    except Exception as exc:
        logger.exception("chat.send_failed")
        fail_turn(ctx, exc)
        return Response({"detail": user_message_for(exc)}, status=503)
    return Response(_answer_body(finish_turn(ctx, outcome)))


class ChatStreamView(SSEAcceptMixin, APIView):
    """POST /api/chat/stream/ — the same turn, streamed as server-sent events."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        question, rejection = _validate(request)
        if rejection:
            return rejection
        # Database work on the request thread; only the LLM loop runs on the
        # stream's worker thread (llm/utils/sse.py).
        ctx = start_turn(user=request.user, question=question)
        try:
            precheck_only()
        except CostCapExceededError as exc:
            return single_frame_stream("done", _answer_body(capped_reply(ctx, exc)))
        return stream_turn(
            lambda on_event: run_turn(ctx, on_event=on_event),
            lambda outcome: _answer_body(finish_turn(ctx, outcome)),
            on_failure=lambda exc: fail_turn(ctx, exc),
        )
