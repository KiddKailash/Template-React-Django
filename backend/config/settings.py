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
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

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
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER", required=True),
            "PASSWORD": os.getenv("DB_PASSWORD", required=True),
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

# Optional Chroma (RAG) — remove if unused
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
