"""Tests for the tool-loop and agent runner.

Every test mocks `_post` in `tool_loop` so we never hit OpenRouter.
The pattern: pre-scripted list of OpenRouter response bodies, returned
one at a time. Each body either contains `tool_calls` (loop continues)
or plain `content` (loop returns).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from llm.utils.tool_loop import chat_with_tools
from llm.utils.tools import REGISTRY, read_only_tool


@pytest.fixture(autouse=True)
def _openrouter_settings(settings):
    settings.OPENROUTER_API_KEY = "test-key"
    settings.OPENROUTER_BASE_URL = "https://openrouter.example/api/v1"
    settings.OPENROUTER_DEFAULT_MODEL = "test/default"
    settings.OPENROUTER_HEAVY_MODEL = "test/heavy"
    settings.OPENROUTER_HTTP_REFERER = "https://template.local"
    settings.OPENROUTER_APP_TITLE = "Template"
    settings.OPENROUTER_REQUEST_TIMEOUT = 5
    settings.OPENROUTER_MONTHLY_USD_CAP = 0
    settings.LLM_MAX_TOOL_TURNS = 4


def _completion(content: str = "", tool_calls: list[dict] | None = None) -> dict:
    """Build a fake OpenRouter chat/completions response body."""
    return {
        "model": "test/default",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_cost": "0.0001"},
    }


def test_no_tool_call_returns_immediately():
    with patch("llm.utils.tool_loop._post", side_effect=[_completion("hello")]) as post:
        resp, traces = chat_with_tools(system="s", user="hi", tools=[])
    assert resp.content == "hello"
    assert traces == []
    assert post.call_count == 1


def test_tool_call_dispatched_and_result_returned():
    @read_only_tool(name="test_echo", description="Echo a string back.")
    def _echo(text: str) -> dict:
        return {"echoed": text}

    try:
        tool_call = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "test_echo", "arguments": '{"text": "hi"}'},
        }
        responses = [
            _completion(tool_calls=[tool_call]),
            _completion(content="final"),
        ]
        with patch("llm.utils.tool_loop._post", side_effect=responses) as post:
            resp, traces = chat_with_tools(system="s", user="u", tools=[REGISTRY["test_echo"]])
        assert resp.content == "final"
        assert len(traces) == 1
        assert traces[0].name == "test_echo"
        assert traces[0].result == {"echoed": "hi"}
        assert traces[0].error is None
        assert post.call_count == 2
    finally:
        REGISTRY.pop("test_echo", None)


def test_unknown_tool_returns_error_to_model():
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "no_such_tool", "arguments": "{}"},
    }
    responses = [
        _completion(tool_calls=[tool_call]),
        _completion(content="ok"),
    ]
    with patch("llm.utils.tool_loop._post", side_effect=responses):
        _, traces = chat_with_tools(system="s", user="u", tools=[])
    assert traces[0].name == "no_such_tool"
    assert traces[0].error is not None
    assert "unknown tool" in traces[0].error


def test_cap_forces_final_no_tool_call(settings):
    settings.LLM_MAX_TOOL_TURNS = 2

    @read_only_tool(name="test_forever", description="Loop forever.")
    def _forever() -> dict:
        return {"ok": True}

    try:
        tool_call = {
            "id": "call_x",
            "type": "function",
            "function": {"name": "test_forever", "arguments": "{}"},
        }
        # Two capped turns keep asking for the tool, then the final
        # no-tools call returns a plain answer.
        responses = [
            _completion(tool_calls=[tool_call]),
            _completion(tool_calls=[tool_call]),
            _completion(content="wrapped up"),
        ]
        with patch("llm.utils.tool_loop._post", side_effect=responses) as post:
            resp, traces = chat_with_tools(system="s", user="u", tools=[REGISTRY["test_forever"]])
        assert resp.content == "wrapped up"
        assert len(traces) == 2
        assert post.call_count == 3
    finally:
        REGISTRY.pop("test_forever", None)


def test_response_accumulates_cost_across_turns():
    @read_only_tool(name="test_cost", description="Return one row.")
    def _cost() -> dict:
        return {"ok": True}

    try:
        tool_call = {
            "id": "call_c",
            "type": "function",
            "function": {"name": "test_cost", "arguments": "{}"},
        }
        responses = [
            _completion(tool_calls=[tool_call]),
            _completion(content="done"),
        ]
        with patch("llm.utils.tool_loop._post", side_effect=responses):
            resp, _ = chat_with_tools(system="s", user="u", tools=[REGISTRY["test_cost"]])
        assert resp.prompt_tokens == 20
        assert resp.completion_tokens == 10
        assert resp.cost_usd == Decimal("0.0002")
    finally:
        REGISTRY.pop("test_cost", None)


def test_missing_api_key_raises(settings):
    settings.OPENROUTER_API_KEY = ""
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        chat_with_tools(system="s", user="u", tools=[])
