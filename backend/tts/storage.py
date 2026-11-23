"""Where audio lives: static files (git + whitenoise), an S3-compatible bucket, or PostgreSQL."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx
from django.conf import settings

from .models import TtsAudio


def s3_enabled() -> bool:
    return bool(settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY)


def static_path(key: str):
    return settings.TTS_STATIC_DIR / f"{key}.mp3"


def static_url(key: str) -> str:
    return f"/{settings.STATIC_URL.strip('/')}/tts/{key}.mp3"


def s3_url(key: str) -> str:
    base = settings.S3_PUBLIC_URL or f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET}"
    return f"{base.rstrip('/')}/tts/{key}.mp3"


def find(key: str) -> str | None:
    """URL of existing audio, without calling the provider."""
    if static_path(key).exists():
        return static_url(key)
    row = TtsAudio.objects.filter(key=key).values("url").first()
    if row:
        return row["url"] or f"/api/tts/audio/{key}.mp3"
    if s3_enabled():
        try:
            if httpx.head(s3_url(key), timeout=5).status_code == 200:
                return s3_url(key)
        except httpx.HTTPError:
            pass
    return None


def save_static(key: str, data: bytes) -> None:
    path = static_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")  # an interrupted run never leaves half a file
    tmp.write_bytes(data)
    tmp.replace(path)


def save_s3(key: str, data: bytes) -> str:
    """PUT with AWS Signature V4 (no SDK)."""
    endpoint = settings.S3_ENDPOINT_URL or f"https://s3.{settings.S3_REGION}.amazonaws.com"
    url = f"{endpoint.rstrip('/')}/{settings.S3_BUCKET}/tts/{key}.mp3"
    parts = urlsplit(url)
    now = datetime.now(UTC)
    stamp, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    digest = hashlib.sha256(data).hexdigest()
    headers = {
        "cache-control": "public, max-age=31536000, immutable",
        "content-type": "audio/mpeg",
        "host": parts.netloc,
        "x-amz-content-sha256": digest,
        "x-amz-date": stamp,
    }
    signed = ";".join(sorted(headers))
    canonical = "\n".join(
        ["PUT", quote(parts.path), "", *[f"{k}:{headers[k]}" for k in sorted(headers)], "", signed, digest]
    )
    scope = f"{day}/{settings.S3_REGION}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = f"AWS4{settings.S3_SECRET_ACCESS_KEY}".encode()
    for piece in (day, settings.S3_REGION, "s3", "aws4_request"):
        k = hmac.new(k, piece.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={settings.S3_ACCESS_KEY_ID}/{scope}, SignedHeaders={signed}, Signature={sig}"
    )
    httpx.put(url, content=data, headers=headers, timeout=20).raise_for_status()
    return s3_url(key)
