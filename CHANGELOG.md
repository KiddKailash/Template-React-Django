# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Web Push notifications** (`backend/notifications/`, from LLMStockAnalysis). `notify()` sends each notification on one channel: push to devices that opened the app in the last 14 days, otherwise (or when the push reaches no device) email. Subscriptions are tied to device sessions: Settings → Devices shows which devices receive pushes, and ending a session stops them. Settings → Notifications: where notifications go, the per-device switch, and a production-safe **test notification** (throttled). Custom service worker (push + click routing), hourly/foreground update polling, PNG icons, `gen_vapid_keys`, daily `dispatch_pending_pushes` backstop, generic HTML email template, `allows()` opt-out hook. Differences from LLMStockAnalysis: pushes carry a 24 h TTL (it sends TTL 0, so a sleeping or offline phone never gets them); sign-out unsubscribes the browser (so the next user is not re-registered on the previous user's permission); no read-tracking endpoint (its service worker calls it without the bearer token, so it can never succeed).
- **Device sessions** (`backend/accounts/`, from LLMStockAnalysis). Each sign-in is a `DeviceSession` bound into the JWTs (`sid`), checked on every request, so sign-out is real: `POST /api/auth/logout/` ends this device, and **Settings → Devices** lists every signed-in device (browser/OS, IP, last active) and signs any or all others out immediately. Refresh extends a live session and is refused for an ended one.
- **Change password** (`POST /api/auth/password/`, from Store-Arbitrage) with Django's validators; keeps this device and signs out every other.
- **Settings page** (`/settings`: Account, Devices, Appearance), an app header (Settings, Sign out), and `?next=` after sign-in (same-site paths only).
- **API hardening** (from Store-Arbitrage): DRF throttles (`anon`, `user`, and `auth` 20/hour per IP on sign-in), JSON-only rendering outside DEBUG, `OPTIONS` without docstrings, `DJANGO_BEHIND_TLS` (https redirect, HSTS, Secure cookies), stdout `LOGGING`.
- **nginx edge hardening** (from Store-Arbitrage/LLMStockAnalysis): real client IP, `$forwarded_scheme`, security headers + baseline CSP, sandboxed `/media/`, `limit_req`, gzip, relative redirects, revalidated SPA shell, immutable `/assets/`.
- `ErrorBoundary` around the routes (from Store-Arbitrage); Vitest with render tests (`npm test`).

### Fixed
- Postgres settings crashed at startup: `os.getenv(..., required=True)` is not a thing (TypeError whenever `DB_NAME` was set). Now an explicit `ImproperlyConfigured` when `DB_USER`/`DB_PASSWORD` are missing.
- nginx forwarded its own `$scheme` (always `http` behind a tunnel) as `X-Forwarded-Proto`.
- File uploads: the axios instance no longer forces `Content-Type: application/json` (it turned `FormData` into JSON → 415). A missing `VITE_BACKEND_URL` no longer produces `undefined/api`.
- Sign-out only forgot the tokens locally; they stayed valid for up to 14 days.
- The service worker cached every `/api/` response for 24 h (per-user data, readable after sign-out); it now caches the app shell only, and sign-out deletes the old cache.

### Changed
- Chroma is disabled by default and kept as infrastructure: the `chroma` service sits behind compose profile `chroma` (backend dependency `required: false`), the deploy starts it only when the profile is active, and the Makefile's chroma dump/restore is opt-in (`WITH_CHROMA=1`). Delete the `profiles:` line to enable. No backend code used it.

### Fixed
- nginx can no longer be OOM-killed by a large upload, a large response or slow downloads. Temp-file spooling and autotuned TCP buffers both count against its 64 MB `mem_limit`: responses are never spooled (`proxy_max_temp_file_size 0`), bodies are limited to 8m (was 50m), with a commented streaming-upload location for bigger files, and the service's `sysctls` cap socket buffers at 512 KB. Measured on pi-zone 2026-11-03.

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
