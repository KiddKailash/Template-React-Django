FROM python:3.14-slim AS deps
LABEL keep-cache="true"

# System deps needed to build psycopg2 + curl for the compose healthcheck
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Move virtual environment outside of /app so host bind-mounts don't overwrite it
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Cache dependency install layer
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev

FROM deps AS final
LABEL keep-cache="false"
COPY . .

RUN uv sync --frozen --no-dev || uv sync --no-dev

# Collect static files with dummy env so settings.py doesn't fail at build time
RUN SECRET_KEY=build-time-placeholder \
    DJANGO_DEBUG=true \
    uv run python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--timeout", "60", "--graceful-timeout", "30", "config.wsgi:application"]
