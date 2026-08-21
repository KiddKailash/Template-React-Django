# Pi 5 Deployment Runbook

This document is the "source of truth" for deploying this template to a Raspberry Pi 5 behind a Cloudflare Tunnel.

Replace `<PROJECT>`, `<USER>`, and `<DOMAIN>` with your specifics before treating this as literal.

## Target System

- **Hardware:** Raspberry Pi 5 (8 GB or 16 GB recommended)
- **Storage:** NVMe SSD (much faster than SD; boot from SSD if possible)
- **OS:** Debian 13 (Trixie) — Lite (CLI only)
- **Network:** Cloudflare Tunnel (`cloudflared`) — no inbound ports open
- **User:** `<USER>` (home: `/home/<USER>`)

## One-time host setup

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Cloudflared
curl -fsSL https://pkg.cloudflare.com/install.sh | sudo bash
sudo apt-get install -y cloudflared

# Self-hosted GitHub Actions runner
mkdir -p ~/actions-runner && cd ~/actions-runner
# Follow: GitHub repo → Settings → Actions → Runners → New self-hosted runner (Linux ARM64)
```

## Directory Structure

The project uses a **Self-Hosted GitHub Actions Runner**:

- **Runner root:** `/home/<USER>/actions-runner/`
- **Work dir:** `/home/<USER>/actions-runner/_work/<PROJECT>/<PROJECT>/`

**⚠️ Persistence warning:** `actions/checkout@v4` cleans the work directory on each run. Never store persistent files (uploads, `.env`, SQLite) directly in repo subfolders — always mount them to Docker Volumes (see `docker-compose.yml`).

## Docker Architecture

Managed by `docker-compose.yml` in the repo root.

- **nginx (frontend):** `${NGINX_HOST_PORT}` → serves the React SPA + proxies `/api/` and `/admin/` to backend. The port is required, not defaulted — see *Host port* below.
- **backend (Django):** Gunicorn on port 8000. `uv` for deps.
- **db (Postgres):** Service name `db`. Internal `db:5432`.
- **chroma (optional):** Service name `chroma`. Internal `chroma:8000`. Remove if not using RAG.

Persistent volumes:
- `media_data` — user uploads (mounted read-only in nginx, read-write in backend)
- `postgres_data` — database data on the NVMe SSD
- `chroma_data` — vector store (`/data` inside the Chroma container)

## Secret Management

**No `.env` files are stored in Git.** Store them as GitHub repository secrets and materialize them at deploy time:

- **`BACKEND_ENV`** — multi-line block; contents of `backend/.env`
- **`FRONTEND_ENV`** — multi-line block; contents of `frontend/.env`
- **`ROOT_ENV`** *(optional)* — compose-only variables that are **not** in
  `backend/.env`. Needed only when the two use different names for the same
  thing — e.g. compose wants `POSTGRES_USER` while Django reads `DB_USER`.

The `deploy.yml` workflow recreates both `.env` files on every push **before** the Docker build starts.

**CSRF safety:** `CSRF_TRUSTED_ORIGINS` in `BACKEND_ENV` must include `https://<DOMAIN>`.

## Host port

The host port is **not** a secret and **not** in the repo. It lives in a file on
the deploy box, named after the compose project:

```bash
mkdir -p ~/deploy
echo 'NGINX_HOST_PORT=8092' > ~/deploy/<PROJECT>.env    # <PROJECT> == `name:` in docker-compose.yml
```

`deploy.yml` builds the project-root `.env` by layering, in this order:

```
backend/.env            app config + credentials     (from BACKEND_ENV)
secrets.ROOT_ENV        compose-only vars, if any
~/deploy/<PROJECT>.env  host-owned facts             (NGINX_HOST_PORT)
```

Compose resolves duplicate keys **last-wins**, so the host file always beats a
stale value left inside a secret. If the file is missing, the deploy fails with
a message naming it rather than falling back to a guessed port.

**Why not a secret.** A host port is a property of the host, not of the
repository. A secret is invisible from the box, cannot be validated against
what is already bound before a deploy runs, and couples the repo to one machine
— so the same `deploy.yml` stops being safe to carry in a fork. Keeping the port
on the host is also what makes it possible to keep an authoritative port table
next to the box instead of inside a CI provider.

**Never give it a default.** `${NGINX_HOST_PORT:-80}` looks harmless until a
second project inherits it and its next deploy binds the port already serving a
live site. Use `${NGINX_HOST_PORT:?...}` so a missing value stops the deploy.

## Cloudflare Tunnel

- **Binary:** `cloudflared` installed as a systemd service.
- **Config path:** `/home/<USER>/.cloudflared/config.yml`
- **Auth:** `cloudflared tunnel login`, then `cloudflared tunnel create <PROJECT>`.
- **Ingress:** Route `<DOMAIN>` → `http://localhost:<NGINX_HOST_PORT>` (the nginx container) — the same port you put in `~/deploy/<PROJECT>.env`.

Example `config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/<USER>/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: <DOMAIN>
    service: http://localhost:<NGINX_HOST_PORT>
  - hostname: www.<DOMAIN>
    service: http://localhost:<NGINX_HOST_PORT>
  - service: http_status:404
```

Then:

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

## First Deploy

1. Replace the three `changeme` placeholders — `name:` and `image:` in
   `docker-compose.yml`, `PROJECT:` in `.github/workflows/deploy.yml`. The
   workflow's preflight step fails the build until all three are done.
2. Add `BACKEND_ENV` and `FRONTEND_ENV` as repo secrets.
3. Create `~/deploy/<PROJECT>.env` on the Pi with `NGINX_HOST_PORT` (see
   *Host port* above), using a port nothing else has claimed.
4. Push to `main`. The workflow will:
   - Check the placeholders are gone
   - Materialize `.env` files from secrets, then layer the root `.env`
   - Hash dependency manifests
   - Build the frontend, atomically swap `dist/` into the nginx mount
   - Build the backend image (or hot-reload if deps unchanged)
   - Rolling restart chroma → db → backend → nginx
   - Run `seed_users` to bootstrap accounts
5. Visit `https://<DOMAIN>`.

## Cron

Host cron (not container cron — survives image rebuilds):

```bash
crontab /home/<USER>/actions-runner/_work/<PROJECT>/<PROJECT>/backend/cron/crontab.txt
```

Edit `backend/cron/crontab.txt` first to fill in `<USER>` and `<PROJECT>`.

## Troubleshooting

- Logs: `docker compose logs -f [service]`
- Force rebuild: `docker compose up -d --build --force-recreate`
- Disk usage: `df -h`

**`required variable BACKEND_IMAGE_HASH is missing a value`** — you are running
`docker compose` by hand, outside the workflow that sets it. Read the tag off
the running container and export it:

```bash
export BACKEND_IMAGE_HASH=$(docker inspect -f '{{.Config.Image}}' <PROJECT>-backend-1 | cut -d: -f2)
```

**`required variable NGINX_HOST_PORT is missing a value`** — `~/deploy/<PROJECT>.env`
is missing, or you are running outside the deploy directory. Both are deliberate:
the alternative is a default that silently binds someone else's port.

**A deploy that hangs instead of failing** is almost always a healthcheck that
never turns green, with `depends_on: condition: service_healthy` waiting on it:

```bash
docker ps --filter health=unhealthy
docker inspect --format '{{json .State.Health}}' <container> | python3 -m json.tool | tail -20
```

Two known causes. Django answers the backend probe with **400** unless
`DJANGO_ALLOWED_HOSTS` includes `localhost` — the probe connects over loopback,
so the public hostname alone is not enough. And the `chroma` image ships **no
curl, wget, nc or python**, so its healthcheck uses `bash` + `/dev/tcp`;
"simplifying" that to `curl` makes it fail forever and hangs everything that
waits on it.
- Tunnel status: `sudo systemctl status cloudflared`
- Runner status: `sudo systemctl status actions.runner.<repo>.<name>` (or check `~/actions-runner/svc.sh status`)
