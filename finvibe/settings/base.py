"""
FinVibe — Base settings shared across all environments.
"""
import os
from pathlib import Path
from decouple import config, Csv

# ─── Paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ─── Security ───────────────────────────────────────────────────────
SECRET_KEY = config("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:8000,http://127.0.0.1:8000",
    cast=Csv(),
)

# ─── Applications ──────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Local
    "invoices",
]

# ─── Middleware ─────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "invoices.middleware.RateLimitMiddleware",
]

# ─── URL / WSGI ────────────────────────────────────────────────────
ROOT_URLCONF = "finvibe.urls"
WSGI_APPLICATION = "finvibe.wsgi.application"

# ─── Templates ──────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ─── Password Validation ───────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Internationalization ──────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ─── Static Files ──────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ─── Media Files ────────────────────────────────────────────────────
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ─── Default PK ────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Auth ──────────────────────────────────────────────────────────
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ─── AI Service ────────────────────────────────────────────────────
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
GEMINI_MODEL = config("GEMINI_MODEL", default="gemini-1.5-flash")
AI_CONFIDENCE_THRESHOLD = config("AI_CONFIDENCE_THRESHOLD", default=0.6, cast=float)
AI_MAX_RETRIES = config("AI_MAX_RETRIES", default=3, cast=int)
AI_REQUEST_TIMEOUT = config("AI_REQUEST_TIMEOUT", default=30, cast=int)
DEMO_MODE = config("DEMO_MODE", default=False, cast=bool)

# ─── Rate Limiting ─────────────────────────────────────────────────
RATE_LIMIT_PER_MINUTE = config("RATE_LIMIT_PER_MINUTE", default=30, cast=int)
RATE_LIMIT_PARSE_PER_MINUTE = config("RATE_LIMIT_PARSE_PER_MINUTE", default=5, cast=int)
MAX_RAW_TEXT_LENGTH = config("MAX_RAW_TEXT_LENGTH", default=50000, cast=int)

# ─── Session Security ─────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True

# ─── Logging ───────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {module}.{funcName}:{lineno} — {message}",
            "style": "{",
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "finvibe.log",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "invoices": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "ai_service": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
