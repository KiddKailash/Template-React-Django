"""Chat engine tests — mocks `chat_with_tools` so no LLM is contacted."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from chat.models import ChatMessage
from llm.models import AgentRun
from llm.utils.openrouter import LLMResponse


@pytest.fixture(autouse=True)
def _llm_configured(settings):
    # The views refuse with 503 before doing anything when no key is set.
    settings.OPENROUTER_API_KEY = "test-key"


@pytest.fixture
def user(db):
    User = get_user_model()
    return User.objects.create_user(username="alice", password="pw")


@pytest.fixture
def authed_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _mock_llm(content: str = "hi there"):
    resp = LLMResponse(
        content=content,
        model="test/default",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=Decimal("0.0001"),
        raw={},
    )
    return resp, []


def test_send_persists_user_and_assistant_and_agent_run(authed_client, user, settings):
    settings.OPENROUTER_MONTHLY_USD_CAP = 0

    with patch("chat.utils.engine.chat_with_tools", return_value=_mock_llm("hello!")):
        r = authed_client.post("/api/chat/", {"message": "hi"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["assistant_message"]["content"] == "hello!"
    assert body["cost_capped"] is False

    msgs = ChatMessage.objects.filter(user=user).order_by("created_at")
    assert [m.role for m in msgs] == ["user", "assistant"]

    run = AgentRun.objects.get()
    assert run.kind == AgentRun.Kind.CHAT
    assert run.status == AgentRun.Status.COMPLETED
    assert run.model_used == "test/default"


def test_send_returns_capped_message_when_budget_blown(authed_client, settings):
    settings.OPENROUTER_MONTHLY_USD_CAP = 0.0001

    # Seed a prior run that eats the entire budget.
    AgentRun.objects.create(
        kind=AgentRun.Kind.CHAT,
        status=AgentRun.Status.COMPLETED,
        cost_usd=Decimal("1.0000"),
    )

    r = authed_client.post("/api/chat/", {"message": "hi"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["cost_capped"] is True
    assert "cap" in body["assistant_message"]["content"].lower()


def test_send_rejects_empty_message(authed_client):
    r = authed_client.post("/api/chat/", {"message": "   "}, format="json")
    assert r.status_code == 400


def test_send_rejects_long_message(authed_client):
    r = authed_client.post("/api/chat/", {"message": "x" * 5000}, format="json")
    assert r.status_code == 400


def test_send_requires_authentication():
    c = APIClient()
    r = c.post("/api/chat/", {"message": "hi"}, format="json")
    assert r.status_code == 401


def test_today_thread_returns_only_this_users_messages(authed_client, user, db):
    User = get_user_model()
    other = User.objects.create_user(username="eve", password="pw")

    from datetime import UTC, datetime

    today = datetime.now(tz=UTC).date()
    ChatMessage.objects.create(user=user, date=today, role="user", content="mine")
    ChatMessage.objects.create(user=other, date=today, role="user", content="theirs")

    r = authed_client.get("/api/chat/today/")
    assert r.status_code == 200
    contents = [m["content"] for m in r.json()["messages"]]
    assert contents == ["mine"]


def test_send_unconfigured_is_503_and_writes_nothing(authed_client, settings):
    settings.OPENROUTER_API_KEY = ""
    r = authed_client.post("/api/chat/", {"message": "hi"}, format="json")
    assert r.status_code == 503
    assert not ChatMessage.objects.exists()
    assert not AgentRun.objects.exists()


def test_send_failure_is_503_and_marks_the_run_failed(authed_client):
    import requests

    with patch("chat.utils.engine.chat_with_tools", side_effect=requests.Timeout("slow")):
        r = authed_client.post("/api/chat/", {"message": "hi"}, format="json")
    assert r.status_code == 503
    assert "too long" in r.json()["detail"]
    run = AgentRun.objects.get()
    assert run.status == AgentRun.Status.FAILED
    assert "Timeout" in run.error


def test_answer_runs_the_whole_turn_for_non_http_callers(user):
    """`answer()` is the one-call API for cron jobs, scripts and agents."""
    from chat.utils.engine import answer

    with patch("chat.utils.engine.chat_with_tools", return_value=_mock_llm("done")):
        result = answer(user=user, question="hi")
    assert result.assistant_message.content == "done"
    assert AgentRun.objects.get().status == AgentRun.Status.COMPLETED


def test_answer_marks_the_run_failed_and_reraises(user):
    from chat.utils.engine import answer

    with patch("chat.utils.engine.chat_with_tools", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            answer(user=user, question="hi")
    assert AgentRun.objects.get().status == AgentRun.Status.FAILED
