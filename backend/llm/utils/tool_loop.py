"""Multi-turn tool-use loop for OpenRouter.

The model gets up to `LLM_MAX_TOOL_TURNS` (default 10) tool-call turns
before we force a final no-tools answer. That cap is enough for
multi-step investigations (chain 6–8 reads before settling on an
answer) while preventing degenerate loops.

Cache hygiene:
  - The `tools` array gets a trailing `cache_control: ephemeral`
    marker on its last entry. Anthropic treats this as "everything up
    to here is cacheable," so the (potentially large) tool defs are
    paid for once and reused for every subsequent turn.
  - The system block uses the same trick via `_cacheable_system()`.

Cost accounting:
  - Each turn's OpenRouter usage block is summed into the final
    `LLMResponse` so callers see the full bill in one row.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

from .openrouter import LLMResponse, Model, _cacheable_system, _headers, _model_id
from .tools import ToolSpec, available_tools

logger = logging.getLogger(__name__)


@dataclass
class ToolCallTrace:
    """Per-turn record kept for observability + replay."""

    turn: int
    name: str
    arguments: dict[str, Any]
    result: Any
    error: str | None = None


def _max_turns() -> int:
    return int(getattr(settings, "LLM_MAX_TOOL_TURNS", 10))


def _tools_payload(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Format tool specs for OpenRouter with cache_control on the last one."""
    out = [t.openrouter_payload() for t in tools]
    if out:
        out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


def _post(payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        headers=_headers(),
        json=payload,
        timeout=settings.OPENROUTER_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _dispatch_tool(
    name: str, raw_args: str, tools_by_name: dict[str, ToolSpec]
) -> tuple[Any, str | None]:
    """Look up `name` in the per-call tool table and execute it.

    Returns (result, error_message). Errors are stringified and sent
    back to the model as the tool_result content so it can retry or
    apologise; we never raise from inside the loop.
    """
    spec = tools_by_name.get(name)
    if spec is None:
        return None, f"unknown tool: {name!r}"
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError as exc:
        return None, f"bad arguments json: {exc}"
    if not isinstance(args, dict):
        return None, "arguments must be a JSON object"
    try:
        return spec.handler(**args), None
    except TypeError as exc:
        return None, f"bad arguments: {exc}"
    except Exception as exc:  # noqa: BLE001 — surface to model, not crash loop
        logger.exception("tool_loop.handler_failed", extra={"tool": name})
        return None, f"tool error: {exc}"


def chat_with_tools(
    *,
    system: str,
    user: str,
    history: list[dict[str, Any]] | None = None,
    tools: list[ToolSpec] | None = None,
    model: Model = "default",
    max_turns: int | None = None,
) -> tuple[LLMResponse, list[ToolCallTrace]]:
    """Run the model with tools; return `(final_response, traces)`.

    Traces capture every executed tool call across the run so the
    caller can persist them (see `llm.models.LLMToolCall`).

    Pass `tools=None` to use the full auto-discovered set. Pass a
    concrete list to restrict the LLM's tool surface for a specific
    call (e.g. tests, or per-user tool gating).
    """
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    if tools is None:
        tools = available_tools()
    tools_by_name = {t.name: t for t in tools}

    messages: list[dict[str, Any]] = [_cacheable_system(system)]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    tools_payload = _tools_payload(tools)
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = Decimal("0")
    last_raw: dict[str, Any] = {}
    last_model = _model_id(model)
    traces: list[ToolCallTrace] = []

    turn_cap = int(max_turns) if max_turns is not None else _max_turns()

    for turn in range(1, turn_cap + 1):
        payload: dict[str, Any] = {
            "model": _model_id(model),
            "messages": messages,
            "usage": {"include": True},
        }
        if tools_payload:
            payload["tools"] = tools_payload
            payload["tool_choice"] = "auto"

        last_raw = _post(payload)
        usage = last_raw.get("usage") or {}
        prompt_tokens += int(usage.get("prompt_tokens", 0))
        completion_tokens += int(usage.get("completion_tokens", 0))
        cost_usd += Decimal(str(usage.get("total_cost", 0)))
        last_model = last_raw.get("model", last_model)

        message = last_raw["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []

        # No tool calls -> done. Return the text content.
        if not tool_calls:
            return LLMResponse(
                content=message.get("content", "") or "",
                model=last_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                raw=last_raw,
            ), traces

        # Append the assistant turn (with tool_calls) and then one
        # tool message per call before re-asking.
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            result, error = _dispatch_tool(name, raw_args, tools_by_name)
            payload_for_model = {"error": error} if error is not None else {"result": result}
            try:
                arg_dict = json.loads(raw_args or "{}")
                if not isinstance(arg_dict, dict):
                    arg_dict = {"_raw": raw_args}
            except json.JSONDecodeError:
                arg_dict = {"_raw": raw_args}
            traces.append(
                ToolCallTrace(
                    turn=turn,
                    name=name,
                    arguments=arg_dict,
                    result=result,
                    error=error,
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(payload_for_model, default=str),
                }
            )

    # Hit the cap — force one more call WITHOUT tools so the model
    # produces a final answer rather than another tool request.
    final_payload = {
        "model": _model_id(model),
        "messages": messages,
        "usage": {"include": True},
    }
    last_raw = _post(final_payload)
    usage = last_raw.get("usage") or {}
    prompt_tokens += int(usage.get("prompt_tokens", 0))
    completion_tokens += int(usage.get("completion_tokens", 0))
    cost_usd += Decimal(str(usage.get("total_cost", 0)))
    last_model = last_raw.get("model", last_model)
    final = last_raw["choices"][0]["message"]
    logger.info(
        "tool_loop.capped",
        extra={"max_turns": turn_cap, "trace_count": len(traces)},
    )
    return LLMResponse(
        content=final.get("content", "") or "",
        model=last_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        raw=last_raw,
    ), traces
