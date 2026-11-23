"""Neural TTS providers behind one interface. TTS_PROVIDER=google|azure."""

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


PROVIDERS = {"google": GoogleProvider, "azure": AzureProvider}


def get_provider() -> TTSProvider:
    return PROVIDERS.get(settings.TTS_PROVIDER, GoogleProvider)()
