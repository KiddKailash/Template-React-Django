# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — LLM harness + MCP server
- `llm/` app: OpenRouter chat client with `HTTP-Referer`/`X-Title` attribution and Anthropic-style `cache_control` marker on the system block.
- Multi-turn `chat_with_tools()` dispatcher with `LLM_MAX_TOOL_TURNS` cap and a final forced no-tools turn.
- `@read_only_tool` decorator + global `REGISTRY` (`ToolSpec` dataclass) with JSON-schema derived from Python type annotations.
- Boot-time AST validator (`llm.apps.LlmConfig.ready`) that fails startup with file+line if any `@read_only_tool` body calls `.save`/`.delete`/`.create`/`.update`/`.bulk_create`/`.bulk_update`/`.get_or_create`/`.update_or_create`. Skip with `LLM_TOOLS_SKIP_VALIDATION=true`.
- `AgentRun` + `LLMToolCall` audit models covering CHAT/AGENT/CRON/WEBHOOK triggers with PENDING/RUNNING/COMPLETED/FAILED/CAPPED/SUPPRESSED status.
- `llm.utils.cost_cap`: monthly USD cap via `OPENROUTER_MONTHLY_USD_CAP` — precheck + post-call recording, with a friendly "cap hit" completion state.
- Three built-in example tools: `current_time_utc`, `list_recent_users`, `count_users_since`.
- `chat/` app: per-user `ChatMessage` model with per-day thread scoping, `POST /api/chat/` and `GET /api/chat/today/` endpoints.
- `mcp_server/` app: MCP JSON-RPC 2.0 endpoint (`/api/mcp/`) implementing `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`; batch requests supported.
- Bearer-token auth (`Authorization: Bearer mcp_<secret>`), SHA-256 hashed at rest, raw secret shown once. Per-token scope (`tools:*` or `tools:<name>`), per-minute rate limit computed from `McpCallLog` for correctness across gunicorn workers.
- Append-only `McpCallLog` audit trail with SHA-256 argument hash (never the raw arguments).
- Belt-and-suspenders privacy walker at the MCP boundary; no-op by default, pluggable via `_DISALLOWED_KEYS` and `_DISALLOWED_STRING_MARKERS`.
- `manage.py issue_mcp_token` CLI + admin-only `McpTokenViewSet` (`/api/mcp/tokens/`).
- `MCP_ENABLED` kill switch returns 503 without touching the tool registry.
- 59 backend tests covering models, protocol, rate limit, privacy walker, tool loop, cost cap, and registry validation.

## [0.1.0] — Initial template

### Added
- Django + DRF backend scaffold with JWT auth (`core/` app, `config/` settings, WSGI/ASGI).
- Health endpoint (`GET /api/health/`) and `GET /api/me/` example.
- `seed_users` management command bootstrapping `INITIAL_USERS`.
- Pytest suite skeleton with shared `conftest.py` fixtures.
- Ruff lint/format config; Python 3.13 pinned.
- React 19 + Vite 7 + MUI 7 + React Router 7 frontend scaffold.
- Axios client with JWT request/refresh interceptors.
- `UserContext`, `SnackbarContext`, `ThemeContext` (light/dark, persisted).
- PWA scaffolding via `vite-plugin-pwa`.
- Login page + `PrivateRoute` gate + 404 page.
- nginx reverse-proxy config and Pi 5 deployment runbook.
- `docker-compose.yml` with Postgres, backend, nginx, and optional Chroma.
- Self-hosted GitHub Actions deploy workflow with hash-based rebuild skip.
- Dependabot config (uv, npm, actions, docker).
- Makefile for one-command prod → local data sync (Postgres + Chroma + media).
- Root docs: README, ARCHITECTURE, CLAUDE, DESIGN, this CHANGELOG, VERSION.
