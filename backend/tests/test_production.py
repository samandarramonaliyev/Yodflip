"""Production-readiness checks: settings guards, health, SPA, DB media storage, seed-once."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image
from rest_framework.test import APIClient

from core.models import SeedState, StoredFile
from decks.models import Deck
from words.models import Word

BACKEND = Path(__file__).resolve().parents[1]
PROD_ENV = {
    "DEBUG": "false",
    "SECRET_KEY": "x" * 50,
    "ALLOWED_HOSTS": "yodflip.example.com",
    "DATABASE_URL": "postgres://u:p@localhost:5432/db",
    "BOT_API_SECRET": "s" * 32,
}


def load_settings(env: dict) -> subprocess.CompletedProcess:
    """Import config.settings in a clean subprocess with exactly these env vars."""
    clean = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "PYTHONPATH", "TEMP", "TMP")}
    code = (
        "import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings';"
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: None;"  # ignore any local .env
        "from config import settings as s;"
        "print(s.DEBUG, s.SECURE_SSL_REDIRECT, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_HSTS_SECONDS,"
        " s.DATABASES['default']['ENGINE'], s.OCR_MOCK, s.TELEGRAM_MOCK, sorted(s.ALLOWED_HOSTS))"
    )
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env={**clean, **env}, capture_output=True, text=True
    )


def test_production_settings_are_secure():
    r = load_settings(PROD_ENV)
    assert r.returncode == 0, r.stderr
    out = r.stdout.strip()
    assert out.startswith("False True True True 31536000 django.db.backends.postgresql False False")
    assert "yodflip.example.com" in out


def test_render_hostname_is_allowed_automatically():
    r = load_settings({**PROD_ENV, "ALLOWED_HOSTS": "", "RENDER_EXTERNAL_HOSTNAME": "yodflip.onrender.com"})
    assert r.returncode == 0, r.stderr
    assert "yodflip.onrender.com" in r.stdout


@pytest.mark.parametrize(
    "override,message",
    [
        ({"SECRET_KEY": ""}, "SECRET_KEY"),
        ({"ALLOWED_HOSTS": ""}, "ALLOWED_HOSTS"),
        ({"DATABASE_URL": ""}, "DATABASE_URL"),
        ({"DATABASE_URL": "sqlite:///db.sqlite3"}, "SQLite"),
        ({"BOT_API_SECRET": "short"}, "BOT_API_SECRET"),
    ],
)
def test_production_refuses_insecure_config(override, message):
    r = load_settings({**PROD_ENV, **override})
    assert r.returncode != 0
    assert message in r.stderr


@pytest.mark.django_db
def test_health_checks_database():
    r = APIClient().get("/api/health/")
    assert r.status_code == 200
    assert r.json()["db"] is True


@pytest.mark.django_db
def test_spa_serves_index_for_client_routes(settings, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Yodflip</title>", encoding="utf-8")
    settings.FRONTEND_DIST = tmp_path
    r = APIClient().get("/levels/A1")
    assert r.status_code == 200
    assert b"Yodflip" in b"".join(r.streaming_content)
    assert "web.telegram.org" in r["Content-Security-Policy"]
    assert "X-Frame-Options" not in r  # Telegram Web must be able to frame the Mini App
    assert r["Cache-Control"] == "no-cache"
    # API routes and missing build assets are never answered with index.html
    assert APIClient().get("/api/does-not-exist/").status_code == 404
    assert APIClient().get("/assets/index-missing.js").status_code == 404


def jpeg(size=(1600, 1200)):
    buf = io.BytesIO()
    Image.new("RGB", size, "orange").save(buf, format="PNG")
    return SimpleUploadedFile("photo.png", buf.getvalue(), "image/png")


@pytest.mark.django_db
def test_card_images_are_stored_in_database_not_disk(api, user, tmp_path, settings):
    def disk_files():
        return set((BACKEND / "media").rglob("*")) if (BACKEND / "media").exists() else set()

    before = disk_files()
    deck = Deck.objects.create(owner=user, name="Img", track="en")
    r = api.post(
        f"/api/decks/{deck.id}/cards/",
        {"term": "orange", "translation": "apelsin", "image": jpeg()},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    url = r.data["image"]
    assert "/media/cards/" in url and url.endswith(".jpg")
    stored = StoredFile.objects.get()
    assert stored.content_type == "image/jpeg" and stored.size < settings.MAX_CARD_IMAGE_BYTES
    assert disk_files() == before  # nothing written to local disk
    # served back with long cache headers, resized to max 800px
    resp = APIClient().get("/media/" + stored.name)
    assert resp.status_code == 200 and resp["Content-Type"] == "image/jpeg"
    assert "immutable" in resp["Cache-Control"]
    assert max(Image.open(io.BytesIO(resp.content)).size) == 800


@pytest.mark.django_db
def test_card_rejects_non_image(api, user):
    deck = Deck.objects.create(owner=user, name="Img", track="en")
    bad = SimpleUploadedFile("x.png", b"not an image", "image/png")
    r = api.post(f"/api/decks/{deck.id}/cards/", {"term": "x", "translation": "y", "image": bad}, format="multipart")
    assert r.status_code == 400


@pytest.mark.django_db
def test_seed_runs_only_once():
    out = io.StringIO()
    call_command("seed_words", stdout=out)
    assert "Seeded 600 words" in out.getvalue()
    assert SeedState.objects.get(key="words").digest
    Word.objects.filter(pk=Word.objects.first().pk).update(translation_uz="CHANGED")
    out = io.StringIO()
    call_command("seed_words", stdout=out)
    assert "Skipping" in out.getvalue()
    assert Word.objects.filter(translation_uz="CHANGED").count() == 1  # untouched
    call_command("seed_words", "--force", stdout=io.StringIO())
    assert Word.objects.filter(translation_uz="CHANGED").count() == 0
