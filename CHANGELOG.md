# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
