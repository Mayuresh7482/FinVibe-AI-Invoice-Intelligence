"""
FinVibe — Production settings (PostgreSQL + Sentry + HTTPS).
"""
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401,F403

DEBUG = False

# ─── DEMO_MODE override: never use demo mode in production ──────
DEMO_MODE = False

# ─── Database: PostgreSQL for production ──────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="finvibe_db"),
        "USER": config("DB_USER", default="finvibe_user"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "connect_timeout": 10,
            "sslmode": config("DB_SSL_MODE", default="prefer"),
        },
    }
}

# ─── Security hardening ──────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Tighten rate limits for production
RATE_LIMIT_PER_MINUTE = config("RATE_LIMIT_PER_MINUTE", default=20, cast=int)
RATE_LIMIT_PARSE_PER_MINUTE = config("RATE_LIMIT_PARSE_PER_MINUTE", default=3, cast=int)

# ─── Sentry ──────────────────────────────────────────────────────
def _sentry_before_send(event, hint):
    """Strip raw_text and other PII from Sentry error reports."""
    if "extra" in event:
        event["extra"].pop("raw_text", None)
        event["extra"].pop("raw_response", None)
    # Strip from breadcrumbs
    for bc in event.get("breadcrumbs", {}).get("values", []):
        if isinstance(bc.get("data"), dict):
            bc["data"].pop("raw_text", None)
    return event


SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=False,
        environment="production",
        before_send=_sentry_before_send,
    )

