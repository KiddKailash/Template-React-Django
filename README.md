# Template — Django + React

A pre-wired template for a Django REST backend + React (Vite + MUI PWA) frontend, deployed to a self-hosted Raspberry Pi 5 behind a Cloudflare Tunnel via Docker Compose and a self-hosted GitHub Actions runner.

The template ships plugged-in and connected: JWT auth, health endpoint, protected routes, light/dark theme, PWA scaffolding, nginx reverse proxy, CI/CD workflow, dependabot, and a `make data-sync` one-liner for pulling prod state to your dev machine.

**This `main` branch is intentionally empty** — it exists only as a landing page. Pick the branch that matches your OS and feature set below, then follow that branch's own `README.md` for full setup instructions.

---

## Choose your template

Templates are organised as `template/<os>/<variant>`:

| Branch | OS | Variant | Use when |
|---|---|---|---|
| [`template/mac/react-django-web-app`](../../tree/template/mac/react-django-web-app) | macOS / Linux | Base web app | You want the plain Django + React stack. |
| [`template/mac/react-django-llm-harness-mcp`](../../tree/template/mac/react-django-llm-harness-mcp) | macOS / Linux | Base + LLM + MCP | You need an OpenRouter-backed LLM harness, tool-use loop, chat surface, and an MCP JSON-RPC 2.0 server. |
| [`template/windows/react-django-web-app`](../../tree/template/windows/react-django-web-app) | Windows | Base web app | Same as the mac base, with Windows-adapted `.vscode/tasks.json` and setup notes. |
| [`template/windows/react-django-llm-harness-mcp`](../../tree/template/windows/react-django-llm-harness-mcp) | Windows | Base + LLM + MCP | Same as the mac LLM/MCP variant, with Windows-adapted `.vscode/tasks.json` and setup notes. |

The `mac` and `windows` branches for a given variant are functionally identical apart from the developer-tooling layer (VS Code tasks, shell invocations, path handling in docs). Choose based on your dev machine.

The LLM/MCP variants add, on top of the base:

- OpenRouter client with prompt caching
- Multi-turn tool-use loop with a boot-time AST validator that forbids DB writes inside `@read_only_tool`
- Per-user `chat/` surface with a monthly USD cost cap
- MCP JSON-RPC 2.0 server (bearer-token auth, append-only audit log, per-token rate limit)

See `backend/llm/`, `backend/chat/`, `backend/mcp_server/` on those branches.

---

## Getting started

### 1. Pick a branch and clone it directly

```bash
git clone --branch template/mac/react-django-web-app --single-branch \
  https://github.com/KiddKailash/Template-React-Django my-new-project
cd my-new-project
rm -rf .git && git init
```

Swap `template/mac/react-django-web-app` for whichever branch matches your OS and variant.

### 2. Read that branch's `README.md`

Each template branch has its own full `README.md` covering prerequisites, environment variables, local dev, Docker, deployment, and the Pi runbook.

### 3. Rename what needs renaming

Every template's `README.md` lists the files to update (`pyproject.toml`, `package.json`, `vite.config.js`, `Makefile`, etc.) so the new project isn't named after the template.

---

## Prerequisites (all variants)

- Python 3.13
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- PostgreSQL 15 (locally, for dev — SQLite works if `DB_NAME` is empty)
- Docker (for prod / running the compose stack locally)

The LLM/MCP variants additionally need an OpenRouter API key.

---

## Repository layout

- `main` — this landing page.
- `template/mac/*`, `template/windows/*` — the actual templates. Long-lived; treat as sources.
- `dependabot/*` — automated dependency PRs. Leave alone.

For architectural details of any given template, read that branch's `ARCHITECTURE.md`. For UI conventions, `DESIGN.md`. For agent-specific instructions, `CLAUDE.md`.
