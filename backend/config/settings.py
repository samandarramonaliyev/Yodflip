"""Yodflip Django settings.

Everything environment-specific comes from env vars. Production (DEBUG=false) refuses to start
with an insecure configuration (missing SECRET_KEY, SQLite, no allowed hosts, ...).
Local development: put DEBUG=true in the repo-root .env (see .env.example).
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in env(name, default).split(",") if x.strip()]


DEBUG = env_bool("DEBUG", False)

# --- Core security ----------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG is false.")
    SECRET_KEY = "dev-insecure-secret-key"  # local development only

# Render injects RENDER_EXTERNAL_HOSTNAME / RENDER_EXTERNAL_URL automatically.
RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "*" if DEBUG else "")
if RENDER_HOST and RENDER_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_HOST)
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set when DEBUG is false.")

PUBLIC_URL = env("PUBLIC_URL") or env("RENDER_EXTERNAL_URL") or ("http://localhost:5173" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if PUBLIC_URL and PUBLIC_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(PUBLIC_URL)

# The React app is served by Django itself and calls /api/... with relative URLs (same
# origin, also in local dev via the Vite proxy), so no CORS configuration is needed.

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "core",
    "accounts",
    "telegram_auth",
    "words",
    "decks",
    "games",
    "ocr",
    "gamification",
    "telegram_bot",
    "duels",
    "botquiz",
    "exams",
    "tts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.PermissionsPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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

# --- Database ---------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL") or (f"sqlite:///{BASE_DIR / 'db.sqlite3'}" if DEBUG else "")
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL (PostgreSQL) must be set when DEBUG is false.")
if not DEBUG and DATABASE_URL.startswith("sqlite") and not env_bool("ALLOW_SQLITE"):
    # ALLOW_SQLITE is only used for build-time steps such as collectstatic.
    raise ImproperlyConfigured("SQLite is not allowed in production; use PostgreSQL via DATABASE_URL.")
# Neon (or any PostgreSQL): use the connection string as-is, including ?sslmode=require.
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL, conn_max_age=600, conn_health_checks=True, ssl_require=env_bool("DATABASE_SSL", False)
    )
}
if "-pooler." in DATABASE_URL:
    # Neon's pooled endpoint runs PgBouncer in transaction mode: no server-side cursors.
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Static files, the React build and media ---------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Pre-generated speech (manage.py generate_tts), served as /static/tts/<sha256>.mp3
TTS_STATIC_DIR = BASE_DIR / "tts_audio"
STATICFILES_DIRS = [("tts", TTS_STATIC_DIR)] if TTS_STATIC_DIR.exists() else []
# The built React app (frontend/dist). Whitenoise serves its files at the site root
# (/assets/..., /favicon.svg); core.views.spa serves index.html for client-side routes.
FRONTEND_DIST = Path(env("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))  # built by build.sh
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
WHITENOISE_MAX_AGE = 3600


def _immutable_file_test(path: str, url: str) -> bool:
    # Vite emits content-hashed files under /assets/ -> cache forever.
    return url.startswith(("/assets/", "/static/tts/"))  # both are content-addressed


WHITENOISE_IMMUTABLE_FILE_TEST = _immutable_file_test

# Media (card images) is stored in PostgreSQL, never on the container's local disk
# (Render disks are ephemeral). See core.storage.DatabaseStorage.
MEDIA_URL = "/media/"
STORAGES = {
    "default": {"BACKEND": "core.storage.DatabaseStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Upload limits: 10 MB scan images, 2 MB card images
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_CARD_IMAGE_BYTES = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + 1024 * 1024

# --- HTTPS / security headers (production) ------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"  # the SPA view relaxes this for Telegram via CSP frame-ancestors
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]  # platform health checks may use plain HTTP
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = False
    # includeSubDomains / preload would pin HTTPS for every subdomain of a domain we may not own
    # (e.g. *.onrender.com). Enable SECURE_HSTS_INCLUDE_SUBDOMAINS on your own domain if you want it.
    SILENCED_SYSTEM_CHECKS = ["security.W021"] + ([] if SECURE_HSTS_INCLUDE_SUBDOMAINS else ["security.W005"])

# --- API ----------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"auth": "30/min"},
}
if not DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = ("rest_framework.renderers.JSONRenderer",)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=60),
    "ROTATE_REFRESH_TOKENS": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Yodflip API",
    "DESCRIPTION": "Vocabulary games for Uzbek-speaking learners of English and German.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "TrackEnum": "accounts.models.TRACK_CHOICES",
        "CefrLevelEnum": "accounts.models.CEFR_CHOICES",
        "UiLanguageEnum": "accounts.models.UI_LANG_CHOICES",
    },
}

# --- Integrations -------------------------------------------------------------
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-opus-5-5")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME").lstrip("@")
# Mini App short name (BotFather /newapp) for t.me/<bot>/<app>?startapp=... links. Optional.
TELEGRAM_APP_SHORT_NAME = env("TELEGRAM_APP_SHORT_NAME")
# How long the bot quiz shows ✅/❌ before the next question.
QUIZ_FEEDBACK_SECONDS = float(env("QUIZ_FEEDBACK_SECONDS", "1.5"))
# Neural text-to-speech. Without credentials the app uses the browser voice.
TTS_PROVIDER = env("TTS_PROVIDER", "google")
GOOGLE_TTS_CREDENTIALS_JSON = env("GOOGLE_TTS_CREDENTIALS_JSON")
AZURE_TTS_KEY = env("AZURE_TTS_KEY")
AZURE_TTS_REGION = env("AZURE_TTS_REGION")
TTS_DAILY_LIMIT = int(env("TTS_DAILY_LIMIT", "200"))  # new audios per user and day
# Optional S3-compatible bucket for the audio (R2, B2, AWS...)
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL")
S3_BUCKET = env("S3_BUCKET")
S3_REGION = env("S3_REGION", "auto")
S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY")
S3_PUBLIC_URL = env("S3_PUBLIC_URL")
# Webhook path secret / Telegram secret_token and the reminder-cron path secret. Optional:
# derived from SECRET_KEY when empty (see telegram_bot.services).
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET")
BOT_CRON_SECRET = env("BOT_CRON_SECRET")

# Sample OCR data is a development convenience only. In production without an Anthropic key
# the Tesseract fallback is used instead.
OCR_MOCK = env_bool("OCR_MOCK", DEBUG and not ANTHROPIC_API_KEY)
# Mock Telegram login accepts UNSIGNED identities, so it is only ever allowed with DEBUG on.
TELEGRAM_MOCK = DEBUG and env_bool("TELEGRAM_MOCK", not TELEGRAM_BOT_TOKEN)
OCR_DAILY_LIMIT = int(env("OCR_DAILY_LIMIT", "20"))
TELEGRAM_AUTH_MAX_AGE = int(env("TELEGRAM_AUTH_MAX_AGE", str(24 * 3600)))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    # Never write the webhook/cron URL secrets to the logs (e.g. Django's "Forbidden: /bot/cron/...").
    "filters": {"redact_secrets": {"()": "core.logging.RedactSecretsFilter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["redact_secrets"]}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
