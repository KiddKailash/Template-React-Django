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

- **nginx (frontend):** Port 80 → serves the React SPA + proxies `/api/` and `/admin/` to backend.
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

The `deploy.yml` workflow recreates both `.env` files on every push **before** the Docker build starts.

**CSRF safety:** `CSRF_TRUSTED_ORIGINS` in `BACKEND_ENV` must include `https://<DOMAIN>`.

## Cloudflare Tunnel

- **Binary:** `cloudflared` installed as a systemd service.
- **Config path:** `/home/<USER>/.cloudflared/config.yml`
- **Auth:** `cloudflared tunnel login`, then `cloudflared tunnel create <PROJECT>`.
- **Ingress:** Route `<DOMAIN>` → `http://localhost:80` (the nginx container).

Example `config.yml`:

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/<USER>/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: <DOMAIN>
    service: http://localhost:80
  - hostname: www.<DOMAIN>
    service: http://localhost:80
  - service: http_status:404
```

Then:

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

## First Deploy

1. Add `BACKEND_ENV` and `FRONTEND_ENV` as repo secrets.
2. Push to `main`. The workflow will:
   - Materialize `.env` files from secrets
   - Hash dependency manifests
   - Build the frontend, atomically swap `dist/` into the nginx mount
   - Build the backend image (or hot-reload if deps unchanged)
   - Rolling restart chroma → db → backend → nginx
   - Run `seed_users` to bootstrap accounts
3. Visit `https://<DOMAIN>`.

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
- Tunnel status: `sudo systemctl status cloudflared`
- Runner status: `sudo systemctl status actions.runner.<repo>.<name>` (or check `~/actions-runner/svc.sh status`)
