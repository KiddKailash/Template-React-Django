"""Django app config for the LLM harness.

`ready()` force-imports the tool registry and runs the AST validator so
that any write call inside a `@read_only_tool` fails boot loudly with
file + line. Skip validation with `LLM_TOOLS_SKIP_VALIDATION=true` for
tests that mock the registry.
"""

from __future__ import annotations

import os

from django.apps import AppConfig


class LlmConfig(AppConfig):
    name = "llm"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        if os.getenv("LLM_TOOLS_SKIP_VALIDATION", "").lower() == "true":
            return
        from .utils.tools import validate_registry

        validate_registry()
