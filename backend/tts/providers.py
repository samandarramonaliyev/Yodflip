"""Neural TTS providers behind one interface: google | azure | elevenlabs.

Words and sentences are routed separately (TTS_WORDS_PROVIDER, TTS_SENTENCES_PROVIDER); see `chain`.
"""

from __future__ import annotations

import base64
import html
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import jwt
from django.conf import settings

log = logging.getLogger(__name__)

RATES = {"normal": 0.95, "slow": 0.7}


class TtsError(Exception):
    pass


class QuotaExceeded(TtsError):
    """The provider refuses further requests (credits used up, key revoked, rate limited): use the fallback."""


@dataclass(frozen=True)
class Voice:
    id: str  # what the client asks for: female | male | us | uk
    locale: str  # always the language of the text, e.g. de-DE
    name: str


class TTSProvider(ABC):
    name = ""
    voices: dict[str, list[Voice]] = {}

    def voice(self, lang: str, voice_id: str = "") -> Voice:
        """A voice of exactly this language (unknown ids → the default one)."""
        options = self.voices[lang]
        return next((v for v in options if v.id == voice_id), options[0])

    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    def synthesize(self, text: str, voice: Voice, rate: float) -> bytes: ...


class GoogleProvider(TTSProvider):
    name = "google"
    voices = {
        "de": [Voice("female", "de-DE", "de-DE-Neural2-G"), Voice("male", "de-DE", "de-DE-Neural2-H")],
        "en": [Voice("us", "en-US", "en-US-Neural2-F"), Voice("uk", "en-GB", "en-GB-Neural2-A")],
        "ru": [Voice("female", "ru-RU", "ru-RU-Wavenet-A")],
    }
    _token: tuple[str, float] = ("", 0.0)
    _lock = threading.Lock()

    def _account(self) -> dict | None:
        raw = settings.GOOGLE_TTS_CREDENTIALS_JSON
        if not raw:
            return None
        try:
            acc = json.loads(raw)
        except json.JSONDecodeError:
            log.error("GOOGLE_TTS_CREDENTIALS_JSON is not valid JSON")
            return None
        return acc if acc.get("client_email") and acc.get("private_key") else None

    def configured(self) -> bool:
        return self._account() is not None

    def _access_token(self) -> str:
        with self._lock:
            token, expires = GoogleProvider._token
            if token and expires > time.time() + 60:
                return token
            acc = self._account() or {}
            uri = acc.get("token_uri") or "https://oauth2.googleapis.com/token"
            now = int(time.time())
            claims = {
                "iss": acc["client_email"],
                "scope": "https://www.googleapis.com/auth/cloud-platform",
                "aud": uri,
                "iat": now,
                "exp": now + 3600,
            }
            assertion = jwt.encode(claims, acc["private_key"], algorithm="RS256")
            r = httpx.post(
                uri,
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
                timeout=15,
            )
            r.raise_for_status()
            body = r.json()
            GoogleProvider._token = (body["access_token"], now + int(body.get("expires_in", 3600)))
            return body["access_token"]

    def synthesize(self, text: str, voice: Voice, rate: float) -> bytes:
        try:
            r = httpx.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                headers={"Authorization": f"Bearer {self._access_token()}"},
                json={
                    "input": {"text": text},
                    "voice": {"languageCode": voice.locale, "name": voice.name},
                    "audioConfig": {"audioEncoding": "MP3", "sampleRateHertz": 24000, "speakingRate": rate},
                },
                timeout=20,
            )
            r.raise_for_status()
            return base64.b64decode(r.json()["audioContent"])
        except (httpx.HTTPError, KeyError, ValueError, jwt.PyJWTError) as exc:
            raise TtsError(f"google: {type(exc).__name__} {getattr(getattr(exc, 'response', None), 'status_code', '')}")


class AzureProvider(TTSProvider):
    name = "azure"
    voices = {
        "de": [Voice("female", "de-DE", "de-DE-KatjaNeural"), Voice("male", "de-DE", "de-DE-ConradNeural")],
        "en": [Voice("us", "en-US", "en-US-JennyNeural"), Voice("uk", "en-GB", "en-GB-SoniaNeural")],
        "ru": [Voice("female", "ru-RU", "ru-RU-SvetlanaNeural")],
    }

    def configured(self) -> bool:
        return bool(settings.AZURE_TTS_KEY and settings.AZURE_TTS_REGION)

    def synthesize(self, text: str, voice: Voice, rate: float) -> bytes:
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{voice.locale}">'
            f'<voice name="{voice.name}"><prosody rate="{round((rate - 1) * 100)}%">{html.escape(text)}</prosody>'
            "</voice></speak>"
        )
        try:
            r = httpx.post(
                f"https://{settings.AZURE_TTS_REGION}.tts.speech.microsoft.com/cognitiveservices/v1",
                headers={
                    "Ocp-Apim-Subscription-Key": settings.AZURE_TTS_KEY,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                    "User-Agent": "yodflip",
                },
                content=ssml.encode(),
                timeout=20,
            )
            r.raise_for_status()
            return r.content
        except httpx.HTTPError as exc:
            raise TtsError(f"azure: {type(exc).__name__}")


class ElevenLabsProvider(TTSProvider):
    """One native voice per language. language_code is sent on every request, so German stays German."""

    name = "elevenlabs"
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64"
    # Credits per character (self-serve plans): flash / turbo models cost half.
    CREDITS_PER_CHAR = {"eleven_flash_v2_5": 0.5, "eleven_turbo_v2_5": 0.5, "eleven_flash_v2": 0.5}

    @property
    def voices(self) -> dict[str, list[Voice]]:  # read on every use: settings can change in tests / admin
        return {
            "de": [Voice("default", "de-DE", settings.ELEVENLABS_VOICE_DE)],
            "en": [Voice("default", "en-US", settings.ELEVENLABS_VOICE_EN)],
        }

    @classmethod
    def credits(cls, chars: int) -> float:
        return chars * cls.CREDITS_PER_CHAR.get(settings.ELEVENLABS_MODEL, 1.0)

    def configured(self) -> bool:
        return bool(settings.ELEVENLABS_API_KEY)

    def synthesize(self, text: str, voice: Voice, rate: float) -> bytes:
        try:
            r = httpx.post(
                self.URL.format(voice=voice.name),
                headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
                json={
                    "text": text,
                    "model_id": settings.ELEVENLABS_MODEL,
                    "language_code": voice.locale[:2],
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": max(0.7, rate)},
                },
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise TtsError(f"elevenlabs: {type(exc).__name__}")
        if r.status_code in (401, 402, 429):
            try:
                status = r.json().get("detail", {}).get("status", "")
            except (ValueError, AttributeError):
                status = ""
            raise QuotaExceeded(f"elevenlabs: {r.status_code} {status}".strip())
        if r.status_code != 200 or not r.content:
            raise TtsError(f"elevenlabs: HTTP {r.status_code}")
        return r.content


PROVIDERS = {"google": GoogleProvider, "azure": AzureProvider, "elevenlabs": ElevenLabsProvider}
PAID = {"elevenlabs"}
QUOTA_PAUSE = 3600  # seconds a provider is skipped after a quota error


def get_provider(name: str = "") -> TTSProvider:
    return PROVIDERS.get(name or settings.TTS_PROVIDER, GoogleProvider)()


def sentences_name() -> str:
    return settings.TTS_SENTENCES_PROVIDER or settings.TTS_PROVIDER


def chain(kind: str, lang: str) -> list[TTSProvider]:
    """Providers for a word or a sentence, preferred first, then the other route as the fallback.

    Only providers that have a voice of this language are included (ElevenLabs has no Russian voice here).
    A paid-per-character provider (ElevenLabs) is never a fallback: it is used only where it is preferred.
    """
    words, sentences = settings.TTS_WORDS_PROVIDER, sentences_name()
    names = [words, sentences] if kind == "word" else [sentences, words]
    names = names[:1] + [n for n in names[1:] if n not in PAID]
    out: list[TTSProvider] = []
    for name in dict.fromkeys(n for n in names if n in PROVIDERS):
        p = get_provider(name)
        if lang in p.voices:
            out.append(p)
    return out or [get_provider()]


def any_configured() -> bool:
    names = {settings.TTS_WORDS_PROVIDER, sentences_name()}
    return any(get_provider(n).configured() for n in names if n in PROVIDERS)


def paused(provider: TTSProvider) -> bool:
    from django.core.cache import cache

    return bool(cache.get(f"tts:quota:{provider.name}"))


def pause(provider: TTSProvider) -> None:
    from django.core.cache import cache

    log.warning("TTS provider %s paused for %ss (quota)", provider.name, QUOTA_PAUSE)
    cache.set(f"tts:quota:{provider.name}", 1, QUOTA_PAUSE)
