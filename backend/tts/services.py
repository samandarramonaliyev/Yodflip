from __future__ import annotations

import hashlib
import logging

import httpx
from django.conf import settings
from django.utils import timezone

from . import storage
from .models import TtsAudio
from .providers import RATES, QuotaExceeded, TtsError, TTSProvider, Voice, chain, get_provider, pause, paused
from .text import kind_of

log = logging.getLogger(__name__)
LANGS = ("de", "en", "ru")
MAX_CHARS = 200


class LimitReached(Exception):
    pass


def cache_key(provider: str, voice: Voice, rate: float, text: str) -> str:
    """sha256(provider + voice + rate + lang + normalized text); `text` is the output of spoken_text."""
    raw = "\n".join([provider, voice.name, f"{rate:.2f}", voice.locale, text])
    return hashlib.sha256(raw.encode()).hexdigest()


Candidate = tuple[TTSProvider, Voice, float, str]


def candidates(text: str, lang: str, rate: str = "normal", voice_id: str = "", kind: str = "") -> list[Candidate]:
    """(provider, voice, speed, cache key) in the routing order: preferred provider first, then the fallback."""
    speed = RATES[rate]
    out = []
    for provider in chain(kind or kind_of(text), lang):
        voice = provider.voice(lang, voice_id)
        out.append((provider, voice, speed, cache_key(provider.name, voice, speed, text)))
    return out


def resolve(text: str, lang: str, rate: str = "normal", voice_id: str = "", kind: str = "") -> Candidate:
    return candidates(text, lang, rate, voice_id, kind)[0]


def new_today(user) -> int:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return TtsAudio.objects.filter(created_by=user, created_at__gte=start).count()


def get_url(user, text: str, lang: str, rate: str = "normal", voice_id: str = "", only: str = "") -> str | None:
    """URL of the audio (generated and cached on the first play). None → the browser voice is used.

    Existing audio of any provider in the chain is served first (never generated again). Otherwise the
    preferred provider generates it; on a quota error it is paused and the fallback provider is used.
    """
    if only:  # the admin check page compares one provider at a time
        provider = get_provider(only)
        voice = provider.voice(lang, voice_id) if lang in provider.voices else None
        options = [(provider, voice, RATES[rate], cache_key(only, voice, RATES[rate], text))] if voice else []
    else:
        options = candidates(text, lang, rate, voice_id)
    for *_, key in options:
        url = storage.find(key)
        if url:
            return url
    usable = [c for c in options if c[0].configured() and not paused(c[0])]
    if not usable:
        return None
    if new_today(user) >= settings.TTS_DAILY_LIMIT:
        raise LimitReached
    for provider, voice, speed, key in usable:
        try:
            data = provider.synthesize(text, voice, speed)
            url = storage.save_s3(key, data) if storage.s3_enabled() else ""
        except QuotaExceeded as exc:
            log.warning("TTS quota: %s", exc)
            pause(provider)
            continue
        except (TtsError, httpx.HTTPError) as exc:
            log.warning("TTS failed: %s", exc)
            continue
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
    return None
