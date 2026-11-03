"""POST /api/chat/stream/ — the chat turn as server-sent events.

Coverage:
  ├── streams start → progress → done; done == the JSON endpoint's body
  ├── the turn is saved (user + assistant, run COMPLETED) before done is sent
  ├── response headers: text/event-stream, X-Accel-Buffering: no, no-cache
  ├── a failing turn → error frame, run FAILED, no assistant message
  ├── cost cap → a done frame with the capped reply (no LLM call)
  ├── early rejections stay JSON even when asked for text/event-stream
  │     (empty, too long, unconfigured)
  └── requires authentication
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from chat.models import ChatMessage
from llm.models import AgentRun
from llm.utils.openrouter import LLMResponse

URL = "/api/chat/stream/"
SSE = {"HTTP_ACCEPT": "text/event-stream"}


@pytest.fixture(autouse=True)
def _llm_configured(settings):
    settings.OPENROUTER_API_KEY = "test-key"
    settings.OPENROUTER_MONTHLY_USD_CAP = 0


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="alice", password="pw")


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _fake_loop(content="streamed answer"):
    """A chat_with_tools stand-in that reports progress like the real loop."""

    def run(**kwargs):
        on_event = kwargs.get("on_event") or (lambda event: None)
        on_event({"type": "iteration", "iteration": 1})
        on_event({"type": "tool_start", "name": "current_time_utc", "args": {}})
        on_event(
            {
                "type": "tool_result",
                "name": "current_time_utc",
                "args": {},
                "ok": True,
                "preview": "2026-11-03T12:00:00Z",
            }
        )
        on_event({"type": "iteration", "iteration": 2})
        resp = LLMResponse(
            content=content,
            model="test/default",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=Decimal("0.0001"),
            raw={},
        )
        return resp, []

    return run


def frames(response) -> list[tuple[str, dict | None]]:
    body = b"".join(response.streaming_content).decode()
    out = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith(":"):
            out.append(("comment", None))
            continue
        event = block.split("\n")[0].removeprefix("event: ")
        data = json.loads(block.split("data: ", 1)[1])
        out.append((event, data))
    return out


def test_streams_progress_then_done(client, user):
    with patch("chat.utils.engine.chat_with_tools", side_effect=_fake_loop()):
        response = client.post(URL, {"message": "what time is it?"}, format="json", **SSE)
        got = frames(response)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    assert response["X-Accel-Buffering"] == "no"
    assert "no-cache" in response["Cache-Control"]

    names = [event for event, _ in got]
    assert names == ["start", "iteration", "tool_start", "tool_result", "iteration", "done"]
    done = got[-1][1]
    assert done["assistant_message"]["content"] == "streamed answer"
    assert done["user_message"]["content"] == "what time is it?"
    assert done["cost_capped"] is False

    # Saved before `done` went out, with the same ids.
    msgs = list(ChatMessage.objects.filter(user=user).order_by("created_at"))
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert done["assistant_message"]["id"] == msgs[1].pk
    run = AgentRun.objects.get()
    assert run.status == AgentRun.Status.COMPLETED
    assert run.output == "streamed answer"


def test_done_matches_the_json_endpoint(client):
    with patch("chat.utils.engine.chat_with_tools", side_effect=_fake_loop("same")):
        streamed = frames(client.post(URL, {"message": "q"}, format="json", **SSE))[-1][1]
        plain = client.post("/api/chat/", {"message": "q"}, format="json").json()
    assert set(streamed) == set(plain)
    assert streamed["assistant_message"]["content"] == plain["assistant_message"]["content"]


def test_failed_turn_is_an_error_frame_and_a_failed_run(client, user):
    with patch("chat.utils.engine.chat_with_tools", side_effect=requests.Timeout("slow")):
        got = frames(client.post(URL, {"message": "q"}, format="json", **SSE))

    assert [e for e, _ in got] == ["start", "error"]
    assert "too long" in got[-1][1]["error"]
    assert AgentRun.objects.get().status == AgentRun.Status.FAILED
    assert not ChatMessage.objects.filter(role="assistant").exists()


def test_cost_cap_is_a_done_frame_without_calling_the_model(client, settings):
    settings.OPENROUTER_MONTHLY_USD_CAP = 0.0001
    AgentRun.objects.create(
        kind=AgentRun.Kind.CHAT, status=AgentRun.Status.COMPLETED, cost_usd=Decimal("1")
    )
    with patch("chat.utils.engine.chat_with_tools") as llm:
        got = frames(client.post(URL, {"message": "q"}, format="json", **SSE))
    llm.assert_not_called()
    assert [e for e, _ in got] == ["start", "done"]
    assert got[-1][1]["cost_capped"] is True


@pytest.mark.parametrize(
    ("body", "status"),
    [({"message": ""}, 400), ({"message": "x" * 4001}, 400)],
)
def test_early_rejections_are_json(client, body, status):
    response = client.post(URL, body, format="json", **SSE)
    assert response.status_code == status
    assert response["Content-Type"].startswith("application/json")
    assert "detail" in response.json()
    assert not ChatMessage.objects.exists()


def test_unconfigured_is_503_json(client, settings):
    settings.OPENROUTER_API_KEY = ""
    response = client.post(URL, {"message": "q"}, format="json", **SSE)
    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/json")


def test_requires_auth(db):
    response = APIClient().post(URL, {"message": "q"}, format="json", **SSE)
    assert response.status_code == 401
