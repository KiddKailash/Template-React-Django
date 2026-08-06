# Backend — Django + DRF

See the root [README](../README.md) and [ARCHITECTURE.md](../ARCHITECTURE.md) for context.

## Commands

```bash
uv sync
cp .env.example .env
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Endpoints (public)

- `POST /api/token/` — obtain JWT pair (`username`, `password`)
- `POST /api/token/refresh/` — refresh access token
- `GET  /api/health/` — healthcheck

## Endpoints (auth required)

- `GET /api/me/` — returns the current user

Add project-specific endpoints in `core/urls.py` or new apps.

## Bootstrapping users on first deploy

Set `INITIAL_USERS` in `.env`:

```
INITIAL_USERS=alice:pw1,bob:pw2
```

Then run:

```bash
uv run python manage.py seed_users
```

The CI/CD workflow runs this automatically after each deploy — safe to re-run.
