# Architecture

> Template scaffolding for a Django + DRF backend and a React + Vite + MUI PWA frontend, deployed to a Raspberry Pi 5 behind a Cloudflare Tunnel via Docker Compose and a self-hosted GitHub Actions runner.

This document is the canonical map of the template. For *what the project is and how to run it*, see `README.md`. For *visual / UI standards*, see `DESIGN.md`.

---

## 1. High-level shape

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (React + Vite PWA)                                  │
│    ├── React Router 7  ─────────────────────────┐            │
│    └── axios → /api/* ───────────────┐          │            │
└──────────────────────────────────────┼──────────┼────────────┘
                                       ▼          ▼
                            ┌─────────────────────────────┐
                            │ nginx (reverse proxy + SPA) │
                            └──────┬──────────┬───────────┘
                                   │ /api/    │ /
                                   ▼          ▼
                ┌──────────────────────────┐  ┌────────────────┐
                │ Django + DRF (Gunicorn)  │  │  frontend/dist │
                │  core/ app               │  │  (static SPA)  │
                └──┬───────────┬───────────┘  └────────────────┘
                   │           │
        ┌──────────┘           └────────────┐
        ▼                                   ▼
┌───────────────┐                    ┌──────────────┐
│ PostgreSQL 15 │                    │ Chroma (HTTP)│
│ all app state │                    │  (optional — │
│               │                    │  remove if   │
│               │                    │  not needed) │
└───────────────┘                    └──────────────┘

Scheduled jobs (host cron → orchestrate.sh → manage.py commands)
```

The stack is intentionally simple: one Django app, one React app, one Postgres, one nginx, and optionally one Chroma — all orchestrated by a single `docker-compose.yml` that runs on a self-hosted Raspberry Pi 5 behind a Cloudflare Tunnel. There is **no Redis, no Celery, no message broker**. Async work uses Python `threading` inside the Gunicorn process plus host-level cron.

---

## 2. Repository layout

```
Template-Django-React/
├── backend/                  Django + DRF API (uv + Python 3.13)
│   ├── core/                 The one Django app — replace with your domain app(s)
│   ├── config/               Django settings, root URLs, WSGI/ASGI
│   ├── cron/                 orchestrate.sh + crontab.txt
│   ├── media/                User uploads (mounted volume in prod)
│   ├── Dockerfile
│   ├── manage.py
│   └── pyproject.toml        uv-managed deps + ruff config
├── frontend/                 React 19 + Vite + MUI PWA
│   ├── src/
│   ├── dist/                 Build output (served by nginx; created by build)
│   └── package.json
├── nginx/                    nginx config + Pi deployment guide
├── .github/
│   ├── workflows/deploy.yml  CI/CD (self-hosted runner)
│   └── dependabot.yml
├── docker-compose.yml        chroma (optional) + db + backend + nginx
├── run_chroma.py             Local-dev Chroma runner (port 8001, optional)
├── Makefile                  Data sync from Pi → local
├── README.md                 Setup, env vars, ops runbook
├── DESIGN.md                 UI / design system (authoritative)
├── ARCHITECTURE.md           This file
├── CLAUDE.md                 Agent instructions for this repo
├── CHANGELOG.md
└── VERSION
```

---

## 3. Backend

### 3.1 Stack

- **Python 3.13** (pinned by `pyproject.toml`), managed by **`uv`** (lockfile-first).
- **Django 5.2** + **Django REST Framework** for the JSON API.
- **`djangorestframework-simplejwt`** for auth (24h access / 14d refresh; rotate on refresh).
- **Gunicorn** (4 threads, 60s timeout, max-requests 200 + jitter) is the WSGI server.
- **WhiteNoise** serves Django static files; nginx serves frontend + user media.
- **PostgreSQL 15** is the system of record (`psycopg2-binary`).
- **`ruff`** for lint/format, **`pytest`** + **`pytest-django`** for tests.

### 3.2 The Django apps

Four apps ship in the template — `core` is the starter, the other three carry the LLM harness. Extend / rename them for your domain:

```
backend/
├── core/                        Starter app: auth, /me, /health
│   ├── models.py                ORM models
│   ├── serializers.py           DRF serializers
│   ├── views.py                 HTTP handlers (thin)
│   ├── urls.py                  /api/* routes
│   ├── admin.py                 Django admin registrations
│   ├── apps.py
│   ├── migrations/              Never hand-edit
│   ├── tests/                   pytest test suite
│   ├── management/commands/     Scheduled / one-off commands
│   │   └── seed_users.py        Bootstraps INITIAL_USERS on first deploy
│   └── utils/                   ⚠️ All business logic lives here
├── llm/                         LLM harness (OpenRouter + tool loop + audit)
│   ├── apps.py                  ready() runs AST validator on the tool registry
│   ├── models.py                AgentRun, LLMToolCall (unified audit trail)
│   ├── admin.py
│   ├── tests/
│   └── utils/
│       ├── openrouter.py        chat() — LLMResponse, cache_control marker
│       ├── tool_loop.py         chat_with_tools() — multi-turn dispatcher
│       ├── prompts.py           Domain-neutral defaults
│       ├── cost_cap.py          precheck_only / record_after_call (monthly USD)
│       ├── agent.py             run_agent() high-level entry point
│       └── tools/
│           ├── decorator.py     @read_only_tool + REGISTRY + ToolSpec
│           ├── validator.py     AST walker forbidding writes in tool bodies
│           └── builtin.py       Example tools (current_time, list_recent_users)
├── chat/                        Per-user chat surface using the harness
│   ├── models.py                ChatMessage (user FK, date-scoped thread)
│   ├── views.py                 POST /api/chat/ + GET /api/chat/today/
│   └── utils/engine.py          answer() — persist, call harness, handle cap
└── mcp_server/                  MCP JSON-RPC endpoint (Streamable HTTP, 2025-03-26)
    ├── models.py                McpToken, McpCallLog (append-only audit)
    ├── views.py                 mcp_endpoint + McpTokenViewSet
    ├── urls.py                  /api/mcp/  +  /api/mcp/tokens/
    ├── management/commands/
    │   └── issue_mcp_token.py   CLI to mint bearer tokens
    └── utils/
        ├── auth.py              Bearer-token verification
        ├── rate_limit.py        Per-token, log-based sliding window
        ├── tool_bridge.py       Registry → MCP tool schema + scope filter
        ├── protocol.py          JSON-RPC dispatch (initialize/tools/list/tools/call/ping)
        └── privacy.py           Belt-and-suspenders walker (no-op by default)
```

**Convention (CLAUDE.md):** views stay thin; logic lives in `<app>/utils/`. Models hold data, not behaviour.

### 3.2.1 LLM harness — how the pieces fit

```
   HTTP view (chat.views.send)   or   cron job / webhook
              │                              │
              └───────────► llm.utils.agent.run_agent()
                                      │
              creates llm.models.AgentRun (kind, trigger_type, status=RUNNING)
                                      │
                                      ▼
                    llm.utils.tool_loop.chat_with_tools()
                          ├── OpenRouter /chat/completions (with tools=REGISTRY.payload)
                          ├── on tool_calls: dispatch to REGISTRY[name].handler
                          ├── loop up to LLM_MAX_TOOL_TURNS
                          └── final forced no-tools turn if cap hit
                                      │
                                      ▼
              AgentRun.status = COMPLETED, cost/turn totals recorded
              bulk_create(LLMToolCall) rows for each tool dispatch

Cost cap: llm.utils.cost_cap.precheck_only() at start, record_after_call() after
each API call. Blown-cap runs finish as AgentRun.Status.CAPPED with a friendly
message rather than an exception.

Boot-time safety: llm.apps.LlmConfig.ready() force-imports the registry and runs
an AST walker over every tool body. Any .save / .delete / .create / .update / …
call in a @read_only_tool aborts boot with file+line.
```

### 3.2.2 MCP server — how requests flow

```
Claude Desktop  ──►  POST /api/mcp/  ──►  mcp_server.views.mcp_endpoint
                     Authorization:                 │
                     Bearer mcp_<secret>            │
                                                    ▼
                                         authenticate() → verify SHA-256
                                                    ▼
                                         is_rate_limited() → count McpCallLog
                                                    ▼
                                         parse JSON-RPC body (single or batch)
                                                    ▼
                                         dispatch(method, params, token)
                                          ├─ initialize / ping / tools/list
                                          └─ tools/call
                                              ├─ tool_bridge.find_callable_tool()
                                              │    (registry + scope + source-gate)
                                              ├─ coerce_arguments() from JSON Schema
                                              ├─ spec.handler(**kwargs)
                                              └─ privacy.enforce() belt-and-suspenders
                                                    ▼
                                         McpCallLog row (append-only audit)
                                                    ▼
                                         JSON-RPC envelope back to client
```

Token lifecycle: `manage.py issue_mcp_token --name "Claude Desktop"` prints the
raw secret exactly once; the DB stores only its SHA-256 hash. Revoke via the
admin, the `/api/mcp/tokens/<id>/revoke/` endpoint, or `McpToken.revoke()`.

### 3.3 Configuration (`backend/config/`)

- `settings.py` — single settings file. Reads env from `backend/.env` via `python-dotenv`.
- `urls.py` — root URLConf; mounts `core.urls` under `/api/` and the standard `/admin/`.
- `wsgi.py` — production entry point (Gunicorn).
- `asgi.py` — present but unused in prod.

**Auth:** JWT. Endpoints require `IsAuthenticated` by default. Token endpoints are `POST /api/token/` and `POST /api/token/refresh/`.

**Middleware order:** Security → WhiteNoise → CORS → Session → CSRF → Auth → Messages → XFrameOptions (`SAMEORIGIN`).

**Required env vars** (see README + `backend/.env.example`): `SECRET_KEY`, `DJANGO_DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `DB_*`, `FRONTEND_URL`, `EMAIL_*`, `INITIAL_USERS`, `HEALTHCHECK_URL`.

**LLM / MCP env vars** (all optional; the harness fails cleanly when unset):
`OPENROUTER_API_KEY`, `OPENROUTER_DEFAULT_MODEL`, `OPENROUTER_HEAVY_MODEL`,
`OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_TITLE`,
`OPENROUTER_MONTHLY_USD_CAP` (0 = disabled), `LLM_MAX_TOOL_TURNS`,
`LLM_TOOLS_SKIP_VALIDATION` (tests only), `MCP_ENABLED` (kill switch).

### 3.4 HTTP API surface (`core/urls.py`)

All endpoints under `/api/`. JSON in, JSON out. `IsAuthenticated` unless noted.

**Auth & health (public)**
- `POST /api/token/`, `POST /api/token/refresh/`
- `GET  /api/health/`

**Example authenticated endpoint**
- `GET  /api/me/` — returns the current user.

**Chat (LLM harness demo surface)**
- `POST /api/chat/`         — send a message; response includes the assistant reply.
- `GET  /api/chat/today/`   — today's thread for the requesting user.

**MCP JSON-RPC (bearer-token auth; not JWT)**
- `POST /api/mcp/`          — the Model Context Protocol endpoint. See §3.2.2.
- `GET/POST /api/mcp/tokens/` — admin-only token management API.

Add project-specific endpoints alongside `core/urls.py` or in new apps.

### 3.5 Background work

Two mechanisms, no queue:

1. **In-process threads.** Long-running work spawned from a view runs in a `threading.Thread` and writes status back to the DB so the frontend can poll.
2. **Host cron → `cron/orchestrate.sh <mode>` → `manage.py <command>`.**

### 3.6 Tests

- `core/tests/` — pytest. `conftest.py` at the backend root provides shared fixtures (`user`, `authenticated_client`, factories).
- Run: `cd backend && uv run pytest`.
- Lint: `uv run ruff check . && uv run ruff format .`.

---

## 4. Frontend

### 4.1 Stack

- **React 19** (functional components only; hooks for everything).
- **Vite 7** — dev server + build.
- **MUI 7** — component library. **Always import individually** (`import Box from '@mui/material/Box'`), never via barrel.
- **React Router 7** — `BrowserRouter`.
- **Axios** — single `api` instance with JWT request/refresh interceptors.
- **vite-plugin-pwa** — installable PWA with Workbox runtime caching.

### 4.2 Layout

```
frontend/src/
├── App.jsx              Route table + global providers
├── main.jsx             Vite entry
├── pages/               One per top-level route
│   ├── Home.jsx
│   ├── AuthPage.jsx
│   └── Error404.jsx
├── components/          Shared UI (e.g. PrivateRoute)
├── contexts/            UserContext, SnackbarContext, ThemeContext
├── services/            api.js (axios instance + endpoint wrappers)
├── styles/              theme.js — single source of MUI theme
└── utils/
```

### 4.3 State

No Redux / Zustand. State is React Context + local component state:

- `UserContext` — auth state; reads/writes `access_token` + `refresh_token` in localStorage; exposes `login` / `logout`.
- `SnackbarContext` — global toast singleton.
- `ThemeContext` — light/dark toggle, persisted to localStorage.

### 4.4 API client (`services/api.js`)

Single axios instance at `${VITE_BACKEND_URL}/api`:
- **Request interceptor:** attaches `Authorization: Bearer <access_token>` from localStorage.
- **Response interceptor:** on 401 (and not already retried), refreshes via `/api/token/refresh/`, retries; if refresh fails, redirects to `/login`.

### 4.5 Styling & design system

- **`DESIGN.md` is the authoritative source for all visual decisions** (per CLAUDE.md).
- `src/styles/theme.js` exports `getTheme(mode)` producing a light or dark MUI theme.
- **Never hardcode colours in components** — use `theme.palette.*` so dark mode and contrast work.

### 4.6 Commands

```bash
cd frontend
npm install
npm run dev        # Vite @ http://localhost:5173
npm run build      # → frontend/dist/
npm run lint       # ESLint
npm run preview
```

---

## 5. Infrastructure & deployment

### 5.1 Docker Compose services

| Service | Image | Role |
|---|---|---|
| `chroma` | `chromadb/chroma:1.5.8` | Optional vector store HTTP server. Volume: `chroma_data`. Remove if not needed. |
| `db` | `postgres:15-alpine` | App database. Healthcheck: `pg_isready`. Volume: `postgres_data`. |
| `backend` | Built from `backend/Dockerfile` | Django + Gunicorn. Runs `collectstatic` + `migrate` on startup. Volumes: `./backend`, `media_data`. |
| `nginx` | `nginx:alpine` | Reverse proxy + SPA host. Mounts `nginx/default.conf`, `frontend/dist`, `media_data`. Only published port (`:80`). 50 MB body limit for uploads. |

nginx routes:
- `/api/` → `backend:8000` (60s timeouts)
- `/admin/`, `/static/` → `backend:8000`
- `/media/` → `/app/media` alias
- `/` → SPA static with `try_files … /index.html` fallback

### 5.2 Scheduled jobs

Driven by host cron → `backend/cron/orchestrate.sh <mode>` → `manage.py` commands. See `backend/cron/crontab.txt` for the example schedule; extend `orchestrate.sh` with the commands your project needs.

### 5.3 CI/CD

`.github/workflows/deploy.yml` runs on push to `main` on a **self-hosted runner** (the Pi):

1. Fix file permissions from any prior run.
2. Materialise `backend/.env` and `frontend/.env` from `BACKEND_ENV` / `FRONTEND_ENV` secrets.
3. Hash dependency manifests (`Dockerfile`, `pyproject.toml`, `uv.lock`, `package*.json`).
4. Build the frontend in a throw-away Docker image, extract `dist/`, atomic swap into nginx mount.
5. Rebuild the backend image **only if** dependency hashes changed; otherwise hot-reload code.
6. Rolling restart: chroma → db → backend (scale to 2, then back to 1) → nginx reload.
7. Prune dangling images, remove anything >24h old.
8. `seed_users` to bootstrap accounts on first boot.

### 5.4 Target environment

- **Raspberry Pi 5** (32 GB, 8-core ARM64), Pi OS + Docker Engine.
- Exposed via **Cloudflare Tunnel** — no inbound ports.
- DNS through Cloudflare.
- Setup guide lives in `nginx/README.md`.

---

## 6. Conventions worth knowing

These come from `CLAUDE.md` and the codebase, and matter day-to-day:

- **Business logic in `core/utils/`**, not in views. Views orchestrate; utils do work.
- **React: functional components only.** Page-level state in the page; props down.
- **MUI imports are individual** (`@mui/material/Box`), never barrel.
- **Theme tokens, not hex.** Use `theme.palette.background.default` etc.; both modes depend on it.
- **Don't hand-edit migrations.** Run `makemigrations` + `migrate`.
- **Tooling.** `uv run ruff check . && uv run ruff format .` in `backend/`; `npm run lint` in `frontend/`; `uv run pytest` for tests.
- **`DESIGN.md` is law for UI decisions.** Read before changing anything visual.

---

## 7. Where to look next

- New developer onboarding → `README.md`.
- Visual / UX work → `DESIGN.md`.
- Recent shipped work → `CHANGELOG.md`.
- Pi deployment runbook → `nginx/README.md`.
