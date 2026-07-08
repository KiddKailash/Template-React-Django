"""Prompt templates for the LLM harness.

Two-message convention: a long, stable `system` (cached via
`cache_control: ephemeral`) and a short per-call `user`. Keeping the
system block stable across calls is what makes the prompt cache pay
off.

Project-specific projects should either extend or replace these
strings. `DEFAULT_SYSTEM` is intentionally domain-neutral so a fresh
clone runs without editing before the developer has picked a voice.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_SYSTEM = """You are a helpful assistant embedded in a Django + React
application. Answer the user concisely and directly. When you need
information about the application's data, call the available tools —
never fabricate values. If a question is outside the data or tools you
have, say so plainly rather than guessing.

Keep responses focused. If a short answer suffices, do not pad it. Use
markdown for structure only when it improves scannability (tables for
tabular data, bullet lists for parallel items).
"""


def user_with_context(question: str, context: dict[str, Any] | None = None) -> str:
    """Wrap a user question with an optional JSON context block."""
    if not context:
        return question
    return (
        "Latest context:\n"
        "```json\n" + json.dumps(context, indent=2, default=str) + "\n```\n\n"
        f"Question: {question}"
    )
