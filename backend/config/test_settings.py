"""Settings for pytest: independent of any local .env file."""

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
os.environ["ALWAYS_ON_SCHEDULER"] = ""
os.environ.setdefault("ANTHROPIC_API_KEY", "")
for _name in ("GOOGLE_TTS_CREDENTIALS_JSON", "AZURE_TTS_KEY", "S3_BUCKET"):
    os.environ[_name] = ""

from .settings import *  # noqa: E402,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests
