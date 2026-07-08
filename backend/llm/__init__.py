"""LLM harness — OpenRouter client, multi-turn tool loop, tool registry.

Consumed by `chat/`, `mcp_server/`, and any project-specific agent that
wants to reason over the app's data with the LLM. Handlers live in
`llm.utils.tools` and are registered with the `@read_only_tool`
decorator; the registry is validated at boot to reject write calls.
"""
