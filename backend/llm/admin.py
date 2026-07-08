from __future__ import annotations

from django.contrib import admin

from .models import AgentRun, LLMToolCall


class LLMToolCallInline(admin.TabularInline):
    model = LLMToolCall
    extra = 0
    readonly_fields = ("turn_index", "tool_name", "arguments", "result", "error", "created_at")
    can_delete = False


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "trigger_type",
        "status",
        "model_used",
        "cost_usd",
        "started_at",
    )
    list_filter = ("kind", "status")
    search_fields = ("trigger_type", "output", "error")
    readonly_fields = (
        "kind",
        "trigger_type",
        "trigger_data",
        "output",
        "status",
        "suppressed_reason",
        "model_used",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "error",
        "started_at",
        "completed_at",
    )
    inlines = [LLMToolCallInline]


@admin.register(LLMToolCall)
class LLMToolCallAdmin(admin.ModelAdmin):
    list_display = ("id", "tool_name", "turn_index", "agent_run", "created_at")
    list_filter = ("tool_name",)
    search_fields = ("tool_name",)
    readonly_fields = (
        "agent_run",
        "turn_index",
        "tool_name",
        "arguments",
        "result",
        "error",
        "created_at",
    )
