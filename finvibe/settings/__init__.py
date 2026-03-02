"""
FinVibe settings — auto-select local or production based on env var.
"""
from decouple import config

environment = config("DJANGO_SETTINGS_MODULE", default="finvibe.settings.local")

if environment == "finvibe.settings.production":
    from .production import *  # noqa: F401,F403
else:
    from .local import *  # noqa: F401,F403
