from __future__ import annotations

import hashlib
import logging

import httpx
from django.conf import settings
from django.utils import timezone

from . import storage
from .models import TtsAudio
from .providers import RATES, TtsError, TTSProvider, Voice, get_provider

log = logging.getLogger(__name__)
LANGS = ("de", "en", "ru")
MAX_CHARS = 200


class LimitReached(Exception):
    pass


def cache_key(provider: str, voice: Voice, rate: float, text: str) -> str:
    """sha256(provider + voice + rate + lang + normalized text); `text` is the output of spoken_text."""
    raw = "\n".join([provider, voice.name, f"{rate:.2f}", voice.locale, text])
    return hashlib.sha256(raw.encode()).hexdigest()


def resolve(text: str, lang: str, rate: str = "normal", voice_id: str = "") -> tuple[TTSProvider, Voice, float, str]:
    provider = get_provider()
    voice, speed = provider.voice(lang, voice_id), RATES[rate]
    return provider, voice, speed, cache_key(provider.name, voice, speed, text)


def new_today(user) -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return TtsAudio.objects.filter(created_by=user, created_at__gte=start).count()


def get_url(user, text: str, lang: str, rate: str = "normal", voice_id: str = "") -> str | None:
    """URL of the audio (generated and cached on the first play). None → the browser voice is used."""
    provider, voice, speed, key = resolve(text, lang, rate, voice_id)
    url = storage.find(key)
    if url:
        return url
    if not provider.configured():
        return None
    if new_today(user) >= settings.TTS_DAILY_LIMIT:
        raise LimitReached
    try:
        data = provider.synthesize(text, voice, speed)
        url = storage.save_s3(key, data) if storage.s3_enabled() else ""
    except (TtsError, httpx.HTTPError) as exc:
        log.warning("TTS failed: %s", exc)
        return None
    TtsAudio.objects.get_or_create(
        key=key,
        defaults={
            "lang": lang,
            "voice": voice.name,
            "text": text[:300],
            "data": None if url else data,
            "url": url,
            "created_by": user,
        },
    )
    return url or f"/api/tts/audio/{key}.mp3"
