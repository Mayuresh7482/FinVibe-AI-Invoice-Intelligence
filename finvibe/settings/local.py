"""
FinVibe — Local development settings (SQLite).
"""
from .base import *  # noqa: F401,F403

DEBUG = True

# ─── Database: SQLite for dev ──────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ─── Simpler static storage for dev ───────────────────────────────
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ─── Email backend for dev ────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
