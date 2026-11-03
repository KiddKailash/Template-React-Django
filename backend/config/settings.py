"""Django settings for the template project."""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Load environment variables from backend/.env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Core security
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("DJANGO_DEBUG", "false").lower() == "true":
        SECRET_KEY = "django-insecure-template-dev-only-do-not-use-in-production"
    else:
        raise ImproperlyConfigured("SECRET_KEY environment variable must be set in production")

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]

# Whether TLS terminates in front of this deployment (Cloudflare Tunnel, Caddy).
# Defaults to true, so a missing variable fails closed. Set false only on a
# plain-HTTP deployment (e.g. LAN-only): browsers refuse `Secure` cookies over
# HTTP, which breaks CSRF and admin login. nginx forwards the client's real
# scheme (the `$forwarded_scheme` map in nginx/default.conf), so the redirect
# below cannot loop behind a tunnel. From Store-Arbitrage.
BEHIND_TLS = os.getenv("DJANGO_BEHIND_TLS", "true").lower() == "true"

if not DEBUG and BEHIND_TLS:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # The compose healthcheck probes plain http://localhost:8000/api/health/
    # from inside the container; it must not be redirected to https.
    SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    # Local
    "accounts",
    "notifications",
    "core",
    "llm",
    "chat",
    "mcp_server",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = "SAMEORIGIN"
SECURE_REFERRER_POLICY = None
SECURE_CROSS_ORIGIN_OPENER_POLICY = None


# ---------------------------------------------------------------------------
# CORS / CSRF
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]


# ---------------------------------------------------------------------------
# DRF + JWT
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    # SimpleJWT plus a live DeviceSession check, so signing a device out from
    # Settings takes effect on its next request (accounts/authentication.py).
    "DEFAULT_AUTHENTICATION_CLASSES": ("accounts.authentication.SessionJWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # JSON only outside DEBUG. The browsable renderer prints each view's
    # docstring (maintainer notes) to anyone who opens an API URL in a browser.
    "DEFAULT_RENDERER_CLASSES": (
        ("rest_framework.renderers.JSONRenderer",)
        + (("rest_framework.renderers.BrowsableAPIRenderer",) if DEBUG else ())
    ),
    # The same docstrings, served as JSON to an OPTIONS request.
    "DEFAULT_METADATA_CLASS": "core.metadata.PublicMetadata",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Blunt ceilings against loops and runaway clients.
        "anon": "60/min",
        "user": "120/min",
        # Sign-in, keyed by IP (accounts/throttling.py). Refresh is excluded.
        "auth": "20/hour",
        # "Send a test notification" (notifications/views.py), per user.
        "push_test": "10/hour",
    },
    # REMOTE_ADDR is nginx, so throttles key on X-Forwarded-For. nginx resolves
    # the real client (real_ip, nginx/default.conf) and appends it last, so
    # trusting exactly one entry is right whatever proxies sit in front.
    "NUM_PROXIES": int(os.getenv("DRF_NUM_PROXIES", "1")),
}

# Throttle counters live in the default cache (per-process LocMemCache): a
# runaway guard, reset when gunicorn recycles a worker, not a security control.
# Use a shared CACHES backend (Redis) if that matters.

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
}


# ---------------------------------------------------------------------------
# URLs / templates
# ---------------------------------------------------------------------------

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# Database  https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# Dev fallback: SQLite when DB_NAME is unset.
# ---------------------------------------------------------------------------
if os.getenv("DB_NAME"):
    # os.getenv has no `required=`; this used to raise TypeError at startup.
    db_user, db_password = os.getenv("DB_USER"), os.getenv("DB_PASSWORD")
    if not db_user or not db_password:
        raise ImproperlyConfigured(
            "DB_USER and DB_PASSWORD must both be set (non-empty) when DB_NAME is set"
        )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": db_user,
            "PASSWORD": db_password,
            "HOST": os.getenv("DB_HOST", "db"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")


# ---------------------------------------------------------------------------
# External
# ---------------------------------------------------------------------------

# Optional Healthchecks.io ping URL for cron health monitoring
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "")

# Frontend base URL for deep links in emails
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Chroma (RAG) — off by default; the service sits behind the `chroma` compose
# profile. Unused until a project enables it (README "Chroma for RAG").
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))


# ---------------------------------------------------------------------------
# OpenRouter / LLM harness
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_REQUEST_TIMEOUT = int(os.getenv("OPENROUTER_REQUEST_TIMEOUT", "60"))

# Attribution headers OpenRouter recommends. Show up on the OpenRouter
# dashboard and help distinguish this app's usage from anything else on
# the same key.
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", FRONTEND_URL)
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "Template Django React")

# Model IDs referred to as "default" / "heavy" throughout the codebase.
# Swap the model with an env var, not a code change.
OPENROUTER_DEFAULT_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "anthropic/claude-haiku-4.5")
OPENROUTER_HEAVY_MODEL = os.getenv("OPENROUTER_HEAVY_MODEL", "anthropic/claude-sonnet-4.5")

# Monthly USD cost cap across all AgentRuns. Set to 0 to disable.
OPENROUTER_MONTHLY_USD_CAP = float(os.getenv("OPENROUTER_MONTHLY_USD_CAP", "0"))

# Max tool-use turns inside a single LLM tool loop before we force a
# final no-tools turn (prevents runaway loops).
LLM_MAX_TOOL_TURNS = int(os.getenv("LLM_MAX_TOOL_TURNS", "10"))


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

# Kill switch. When False, `/api/mcp/` returns 503 without touching the
# tool registry. Useful for one-click disable during an incident.
MCP_ENABLED = os.getenv("MCP_ENABLED", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Web Push (notifications/). Generate a keypair with
# `uv run python manage.py gen_vapid_keys`. Empty private key = push off: the
# Settings toggle says so, and notify() falls back to email.
# ---------------------------------------------------------------------------

WEB_PUSH_VAPID_PUBLIC_KEY = os.getenv("WEB_PUSH_VAPID_PUBLIC_KEY", "")
WEB_PUSH_VAPID_PRIVATE_KEY = os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY", "")
# A contact for push services to reach about this sender (RFC 8292). Use an
# address you read; some push services reject example.com.
WEB_PUSH_VAPID_SUBJECT = os.getenv("WEB_PUSH_VAPID_SUBJECT", "mailto:admin@example.com")
# How long a push service keeps a message for a device that is offline or
# asleep. pywebpush's default (0) drops it unless the device is reachable at
# that instant.
WEB_PUSH_TTL_SECONDS = int(os.getenv("WEB_PUSH_TTL_SECONDS", str(24 * 60 * 60)))


# ---------------------------------------------------------------------------
# Logging: one stdout stream with ISO timestamps and logger names, which
# `docker compose logs` and cron redirects keep in order. From Store-Arbitrage.
# ---------------------------------------------------------------------------

APP_LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)-8s %(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["stdout"], "level": "WARNING"},
    "loggers": {
        # Project apps; add yours here.
        **{
            app: {"handlers": ["stdout"], "level": APP_LOG_LEVEL, "propagate": False}
            for app in ("accounts", "notifications", "core", "llm", "chat", "mcp_server")
        },
        "django": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        # Per-request noise; gunicorn already records access lines.
        "django.server": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
        # Chatty at DEBUG, and can leak header values.
        "urllib3": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
    },
}
