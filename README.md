# Template — Django + React + Raspberry Pi 5

A pre-wired template for a Django REST backend + React (Vite + MUI PWA) frontend, deployed to a self-hosted Raspberry Pi 5 behind a Cloudflare Tunnel via Docker Compose and a self-hosted GitHub Actions runner.

The template ships plugged-in and connected: JWT auth, health endpoint, protected routes, light/dark theme, PWA scaffolding, nginx reverse proxy, CI/CD workflow, dependabot, and a `make data-sync` one-liner for pulling prod state to your dev machine.

**Also included: a full LLM harness.** An OpenRouter client with prompt-caching, a multi-turn tool-use loop with a boot-time AST validator that forbids DB writes inside `@read_only_tool`, a per-user `chat/` surface, a monthly USD cost cap, and an MCP JSON-RPC 2.0 server (bearer-token auth, append-only audit log, per-token rate limit). See `backend/llm/`, `backend/chat/`, `backend/mcp_server/`.

For the architectural overview, read [ARCHITECTURE.md](./ARCHITECTURE.md). For UI decisions, read [DESIGN.md](./DESIGN.md). Agent-specific instructions are in [CLAUDE.md](./CLAUDE.md).

---

## Cloning the template

```bash
git clone <this-template> my-new-project
cd my-new-project
rm -rf .git
git init
```

Then rename what needs to be renamed.

**Do these three first — the deploy workflow refuses to run until they are
done.** They all encode the same project name, so pick it once: lowercase,
hyphens, no spaces.

| File | Change |
|------|--------|
| `docker-compose.yml` | `name: changeme` → `name: my-new-project` |
| `docker-compose.yml` | `image: changeme-backend:` → `image: my-new-project-backend:` |
| `.github/workflows/deploy.yml` | `PROJECT: changeme` → `PROJECT: my-new-project` |

The project name prefixes every container and every named volume, so it is
effectively permanent: changing it later orphans the volumes and the app comes
back up with an empty database. That is why it is a placeholder that fails the
build rather than a default that quietly works — a working default gets copied
verbatim, which is how a previous project spent months publishing an image
literally called `app-backend`.

Also worth renaming, but nothing enforces these:

- `backend/pyproject.toml` — `name`, `description`
- `frontend/package.json` — `name`
- `frontend/index.html` — `<title>`
- `frontend/vite.config.js` — PWA manifest name / short_name / description / theme_color
- `.env.example` / `docker-compose.yml` — `POSTGRES_DB` etc. for a per-project DB name
- `Makefile` — `SSH_HOST`, `COMPOSE_PROJECT`, `PGDATABASE`
- `nginx/README.md` — hostname, tunnel ID, paths on the Pi

---

## Prerequisites

- Python 3.13
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- PostgreSQL 15 (locally, for dev)
- Docker (for prod / running the compose stack locally)

---

## Quick Start (local, without Docker)

### 1. Backend

```bash
cd backend
uv sync
cp .env.example .env    # fill in secrets / DB creds
uv run python manage.py migrate
uv run python manage.py runserver   # http://localhost:8000
```

Bootstrap a user:

```bash
uv run python manage.py createsuperuser
# or set INITIAL_USERS in .env and run:
uv run python manage.py seed_users
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env    # fill in VITE_BACKEND_URL
npm run dev             # http://localhost:5173
```

### 3. (Optional) Chroma for RAG

```bash
uv run run_chroma.py    # http://localhost:8001
```

Remove `run_chroma.py`, the `chroma` service in `docker-compose.yml`, and the `CHROMA_*` env vars if you don't need a vector store.

---

## Environment variables

### `backend/.env`

```env
# ── Django ────────────────────────────────────────────────────────────────────
SECRET_KEY=                    # long random string (required in production)
DJANGO_DEBUG=true
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173

# ── Frontend URL (used in email deep links) ───────────────────────────────────
FRONTEND_URL=http://localhost:5173

# ── Initial Users (created by `manage.py seed_users`) ─────────────────────────
# Format: username:password,username2:password2
INITIAL_USERS=

# ── Email (Gmail SMTP with App Password) ──────────────────────────────────────
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=

# ── Monitoring (optional) ─────────────────────────────────────────────────────
HEALTHCHECK_URL=

# ── Database ──────────────────────────────────────────────────────────────────
# ── !! Leave DB_NAME empty to use SQLite3 loclocally in development environment
DB_NAME=app
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=postgres
DB_PORT=5432

# ── Chroma (optional — remove if not using RAG) ───────────────────────────────
CHROMA_HOST=localhost
CHROMA_PORT=8001

# ── OpenRouter / LLM harness ──────────────────────────────────────────────────
OPENROUTER_API_KEY=
OPENROUTER_HTTP_REFERER=http://localhost:5173
OPENROUTER_APP_TITLE=My App
OPENROUTER_DEFAULT_MODEL=anthropic/claude-haiku-4.5
OPENROUTER_HEAVY_MODEL=anthropic/claude-sonnet-4.5
OPENROUTER_MONTHLY_USD_CAP=0        # 0 disables the cap
LLM_MAX_TOOL_TURNS=10

# ── MCP server ────────────────────────────────────────────────────────────────
MCP_ENABLED=true
```

### `frontend/.env`

```env
VITE_BACKEND_URL=http://localhost:8000
```

---

## Running the full stack via Docker

```bash
cp .env.example .env      # what Compose interpolates — see the note below
docker compose up --build # backend/.env and frontend/.env must exist too
```

- SPA + API: <http://localhost:8080/> (whatever `NGINX_HOST_PORT` you set)
- Django admin: <http://localhost:8080/admin/>
- Postgres: internal (`db:5432`)
- Chroma: internal (`chroma:8000`) — remove the service if not needed

**Three env files, three different jobs.** This trips people up, so:

| File | Read by | Contains |
|------|---------|----------|
| `backend/.env` | Django, via `env_file:` | app config, DB credentials, API keys |
| `frontend/.env` | Vite at build time | `VITE_*` vars baked into the bundle |
| `.env` (root) | **Compose itself** | only what appears as `${VAR}` in `docker-compose.yml` |

Compose interpolates `${VAR}` in `docker-compose.yml` from the **root `.env`
only** — never from an `env_file:` directive. So `NGINX_HOST_PORT` and
`BACKEND_IMAGE_HASH` must be in the root `.env`, even though they look like they
belong with everything else. `.env.example` documents both.

Both are declared `${VAR:?message}` rather than `${VAR:-default}`. A missing
value aborts with a message naming the fix, instead of silently binding a port
that belongs to something else or pulling an image tag that was never built.

---

## Deploying to a Raspberry Pi 5

The full runbook (OS flash → Docker → self-hosted runner → env secrets → first deploy → tunnel → cron) is in [`nginx/README.md`](./nginx/README.md).

TL;DR:

1. Install Docker + a self-hosted GitHub Actions runner on the Pi.
2. Replace the three `changeme` placeholders (see *Cloning the template* above).
3. Add `BACKEND_ENV` and `FRONTEND_ENV` as repository secrets (multi-line env content).
4. **On the Pi**, allocate a host port and record it:

   ```bash
   mkdir -p ~/deploy
   echo 'NGINX_HOST_PORT=8092' > ~/deploy/my-new-project.env   # filename == PROJECT
   ```

   The file is named after the compose project name, and the workflow fails with
   a pointer if it is missing. The port lives on the host rather than in a
   GitHub secret because **a host port is a property of the host, not of the
   repository**: the repo declares that it needs a port, the host decides which,
   and neither guesses on the other's behalf. A secret is invisible from the box,
   cannot be checked against what is already bound, and ties the repo to one
   machine.

5. Push to `main` → the workflow builds, deploys, and seeds users.
6. Point a Cloudflare Tunnel at `http://localhost:<NGINX_HOST_PORT>` on the Pi.

---

## Syncing prod data down to your dev machine

The `Makefile` pulls Postgres + Chroma volume + media volume off the Pi over SSH and restores them into your native local Postgres and plain directories.

```bash
# One-liner (edit SSH_HOST + COMPOSE_PROJECT in the Makefile first)
make data-sync

# Or step by step
make data-dump          # -> dumps/
make data-restore-local # -> local postgres + ./.chroma + backend/media
```

---

## Common commands

```bash
# Backend
cd backend
uv run python manage.py runserver
uv run python manage.py migrate
uv run pytest                      # tests
uv run ruff check .
uv run ruff format .

# Frontend
cd frontend
npm run dev
npm run build
npm run lint

# Full stack
docker compose up --build
docker compose logs -f backend

# Data
make data-sync
```

---

## Where things live

| Concern | File / dir |
|---|---|
| Django settings | `backend/config/settings.py` |
| Root URL routing | `backend/config/urls.py` |
| Domain app (rename me) | `backend/core/` |
| Business logic | `backend/core/utils/` |
| LLM harness (OpenRouter + tool loop + audit) | `backend/llm/` |
| `@read_only_tool` registry + AST validator | `backend/llm/utils/tools/` |
| Per-user chat surface | `backend/chat/` |
| MCP JSON-RPC server + bearer tokens | `backend/mcp_server/` |
| Issue a new MCP token | `uv run python manage.py issue_mcp_token --name "Claude Desktop"` |
| Cron entrypoint | `backend/cron/orchestrate.sh` |
| React entry / routes | `frontend/src/App.jsx` |
| Auth flow | `frontend/src/contexts/UserContext.jsx`, `frontend/src/services/authService.js` |
| Axios client | `frontend/src/services/api.js` |
| Theme | `frontend/src/styles/theme.js` |
| nginx config | `nginx/default.conf` |
| Pi runbook | `nginx/README.md` |
| CI/CD | `.github/workflows/deploy.yml` |
| Data sync | `Makefile` |
