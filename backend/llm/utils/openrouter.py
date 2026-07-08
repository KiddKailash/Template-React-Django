"""OpenRouter chat-completion client.

Thin wrapper around OpenRouter's `/chat/completions`. What it does:

  - Sends OpenRouter's recommended attribution headers (`HTTP-Referer`,
    `X-Title`) so calls show up correctly on the OpenRouter dashboard.
  - Marks the system block with Anthropic's
    `cache_control: {"type": "ephemeral"}` so the prompt cache absorbs
    large stable context across successive calls in a short window.
  - Returns a normalised `LLMResponse` with `cost_usd` pulled from
    OpenRouter's `usage` block (populated when `usage.include = true`).

Models live in settings so callers say `"default"` / `"heavy"` rather
than hard-coding IDs — swap the model with an env var, not a code
change. For multi-turn tool use, see `llm.utils.tool_loop.chat_with_tools`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import requests
from django.conf import settings

Model = Literal["default", "heavy"]


@dataclass
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    raw: dict[str, Any]


def _model_id(model: Model) -> str:
    return {
        "default": settings.OPENROUTER_DEFAULT_MODEL,
        "heavy": settings.OPENROUTER_HEAVY_MODEL,
    }[model]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
        "X-Title": settings.OPENROUTER_APP_TITLE,
    }


def _cacheable_system(text: str) -> dict[str, Any]:
    """Format a system message with Anthropic-style ephemeral cache marker."""
    return {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


def chat(
    *,
    system: str,
    user: str,
    history: list[dict[str, str]] | None = None,
    model: Model = "default",
    cache_system: bool = True,
) -> LLMResponse:
    """Single-shot completion (no tools). Use `chat_with_tools` for tool use."""
    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    system_msg = (
        _cacheable_system(system) if cache_system else {"role": "system", "content": system}
    )
    messages: list[dict[str, Any]] = [system_msg]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    payload = {
        "model": _model_id(model),
        "messages": messages,
        "usage": {"include": True},
    }
    resp = requests.post(
        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
        headers=_headers(),
        json=payload,
        timeout=settings.OPENROUTER_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]["message"]
    usage = data.get("usage") or {}
    return LLMResponse(
        content=choice.get("content", "") or "",
        model=data.get("model", _model_id(model)),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        cost_usd=Decimal(str(usage.get("total_cost", 0))),
        raw=data,
    )
