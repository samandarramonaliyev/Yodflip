"""Neural TTS: language, cache, pre-generation, fallback, validation, rate limit."""

import base64
import hashlib
import json
from io import StringIO

import httpx
import pytest
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from accounts.models import User
from tts import providers, services, storage
from tts.models import TtsAudio
from tts.providers import AzureProvider, GoogleProvider, TtsError
from tts.text import spoken_text
from words.models import Pack, Word

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def audio_dir(settings, tmp_path):
    settings.TTS_STATIC_DIR = tmp_path
    settings.TTS_PROVIDER = "google"
    return tmp_path


@pytest.fixture
def google(settings, monkeypatch):
    """Configured provider; records what is sent instead of calling Google."""
    settings.GOOGLE_TTS_CREDENTIALS_JSON = json.dumps({"client_email": "a@b.c", "private_key": "k"})
    sent = []

    def post(url, **kw):
        sent.append((url, kw.get("json")))
        body = {"audioContent": base64.b64encode(b"MP3" + kw["json"]["input"]["text"].encode()).decode()}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(GoogleProvider, "_access_token", lambda self: "tok")
    monkeypatch.setattr(providers.httpx, "post", post)
    return sent


def get(api, text="der Bahnhof", lang="de", **kw):
    return api.get("/api/tts/", {"text": text, "lang": lang, **kw})


@pytest.mark.parametrize(
    "lang,voice,locale",
    [("de", "", "de-DE"), ("de", "male", "de-DE"), ("de", "us", "de-DE"), ("en", "", "en-US"), ("en", "uk", "en-GB")]
    + [("en", "male", "en-US"), ("ru", "", "ru-RU")],
)
def test_language_code_always_matches_the_text(api, google, lang, voice, locale):
    assert get(api, "Test", lang, voice=voice).status_code == 200
    body = google[0][1]
    assert body["voice"]["languageCode"] == locale and body["voice"]["name"].startswith(locale)
    assert body["input"] == {"text": "Test"}
    audio = body["audioConfig"]
    assert (audio["audioEncoding"], audio["sampleRateHertz"], audio["speakingRate"]) == ("MP3", 24000, 0.95)


def test_every_voice_belongs_to_its_language():
    for p in (GoogleProvider, AzureProvider):
        for lang, voices in p.voices.items():
            assert all(v.locale.startswith(lang) and v.name.startswith(v.locale) for v in voices)


def test_second_request_comes_from_the_cache(api, google, client_for):
    first = get(api).data
    other = client_for(User.objects.create_user(email="x@y.z", password="secret123"))
    assert get(other, "  der   Bahnhof ").data["url"] == first["url"]
    assert len(google) == 1
    r = APIClient().get(first["url"])
    assert r.status_code == 200 and r["Content-Type"] == "audio/mpeg" and r.content == b"MP3der Bahnhof"
    assert "immutable" in r["Cache-Control"]
    assert get(api, rate="slow").data["url"] != first["url"] and google[-1][1]["audioConfig"]["speakingRate"] == 0.7


def test_cache_key_is_stable():
    v = GoogleProvider.voices["de"][0]
    raw = "google\nde-DE-Neural2-G\n0.95\nde-DE\nder Bahnhof"
    assert services.cache_key("google", v, 0.95, "der Bahnhof") == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.parametrize(
    "raw,lang,out",
    [
        ("der Bahnhof", "de", "der Bahnhof"),
        ("der Arzt, die Ärztin", "de", "der Arzt"),
        ("der Lehrer / die Lehrerin", "de", "der Lehrer"),
        ("der Lehrer, -in", "de", "der Lehrer"),
        ("🔊 das Mädchen (Pl.)", "de", "das Mädchen"),
        ("aka / uka", "ru", "aka"),
        ("Ja, das Haus ist groß.", "de", "Ja, das Haus ist groß."),
        ("Is he/she here?", "en", "Is he, she here?"),
    ],
)
def test_spoken_text(raw, lang, out):
    assert spoken_text(raw, lang) == out


def test_fallback_without_credentials(api):
    d = get(api).data
    assert d["url"] is None and d["fallback"] is True and d["lang"] == "de"


def test_provider_error_falls_back(api, google, monkeypatch):
    def fail(*a, **k):
        raise TtsError("down")

    monkeypatch.setattr(GoogleProvider, "synthesize", fail)
    assert get(api).data["fallback"] is True and TtsAudio.objects.count() == 0


def test_validation(api, google):
    assert APIClient().get("/api/tts/", {"text": "a", "lang": "de"}).status_code == 401
    for kw in ({"lang": "uz"}, {"lang": "fr"}, {"text": ""}, {"text": "()"}, {"text": "a" * 201}, {"rate": "9"}):
        assert get(api, **kw).status_code == 400, kw
    assert google == []


def test_rate_limit_counts_only_new_audio(api, google, settings):
    settings.TTS_DAILY_LIMIT = 2
    assert get(api, "eins").status_code == get(api, "zwei").status_code == 200
    assert get(api, "drei").status_code == 429
    assert get(api, "eins").status_code == 200


def test_azure_request(api, settings, monkeypatch):
    settings.TTS_PROVIDER, settings.AZURE_TTS_KEY, settings.AZURE_TTS_REGION = "azure", "k", "westeurope"
    sent = []

    def post(url, **kw):
        sent.append(kw["content"].decode())
        return httpx.Response(200, content=b"mp3", request=httpx.Request("POST", url))

    monkeypatch.setattr(providers.httpx, "post", post)
    get(api, "Müller & Söhne", voice="male")
    assert 'xml:lang="de-DE"' in sent[0] and "de-DE-ConradNeural" in sent[0] and "Müller &amp; Söhne" in sent[0]


def test_s3_storage(api, google, settings, monkeypatch):
    settings.S3_BUCKET, settings.S3_ACCESS_KEY_ID, settings.S3_SECRET_ACCESS_KEY = "b", "id", "sec"
    settings.S3_ENDPOINT_URL, settings.S3_PUBLIC_URL = "https://s3.example.com", "https://cdn.example.com"
    puts = []
    ok = httpx.Response(200, request=httpx.Request("PUT", "https://x"))
    monkeypatch.setattr(storage.httpx, "put", lambda url, **kw: puts.append((url, kw)) or ok)
    monkeypatch.setattr(storage.httpx, "head", lambda url, **kw: httpx.Response(404))
    url = get(api).data["url"]
    assert url.startswith("https://cdn.example.com/tts/") and len(puts) == 1
    assert puts[0][1]["headers"]["authorization"].startswith("AWS4-HMAC-SHA256 Credential=id/")
    assert TtsAudio.objects.get().data is None
    assert get(api).data["url"] == url and len(puts) == 1


# --- generate_tts ---------------------------------------------------------------------------
@pytest.fixture
def words(db):
    for track, names in (("de", [("Bahnhof", "der"), ("gehen", "")]), ("en", [("house", "")])):
        pack = Pack.objects.create(track=track, level="A1", slug="p", name_uz="p", name_en="p", name_ru="p")
        for w, art in names:
            Word.objects.create(
                track=track, level="A1", pack=pack, word=w, article=art, part_of_speech="x", definition="d",
                translation_uz="t", example=f"Example {w}.",
            )  # fmt: skip


def run(*args):
    out = StringIO()
    call_command("generate_tts", "--rps", "0", *args, stdout=out, stderr=out)
    return out.getvalue()


def test_generate_is_idempotent_and_resumable(words, google, audio_dir, api):
    run("--limit", "2")
    assert len(google) == 2 and len(list(audio_dir.glob("*.mp3"))) == 2
    run()  # continues
    assert len(google) == 6 and len(list(audio_dir.glob("*.mp3"))) == 6
    assert "der Bahnhof" in [b["input"]["text"] for _, b in google]  # with the article
    run()
    assert len(google) == 6
    # the app serves exactly these files, without the provider or the DB
    assert get(api).data["url"].startswith("/static/tts/") and len(google) == 6 and TtsAudio.objects.count() == 0


def test_generate_dry_run_and_no_credentials(words):
    assert "6 files to generate" in run("--dry-run")
    with pytest.raises(CommandError):
        run()


def test_generate_resumes_after_failures(words, google, audio_dir, monkeypatch):
    real, n = GoogleProvider.synthesize, [0]

    def flaky(self, *a):
        n[0] += 1
        if n[0] > 1:
            raise TtsError("quota")
        return real(self, *a)

    monkeypatch.setattr(GoogleProvider, "synthesize", flaky)
    with pytest.raises(CommandError, match="1 files are done"):
        run()
    monkeypatch.setattr(GoogleProvider, "synthesize", real)
    run()
    assert len(list(audio_dir.glob("*.mp3"))) == 6


# --- admin page -----------------------------------------------------------------------------
def test_check_page_is_staff_only(client, google):
    assert client.get("/admin/tts-check/").status_code == 302
    assert client.get("/admin/tts-check/url/", {"text": "Öl", "lang": "de"}).status_code == 302
    client.force_login(User.objects.create_superuser("a@b.uz", "secret123"))
    html = client.get("/admin/tts-check/").content.decode()
    for w in ("Eichhörnchen", "Straße", "der Ingenieur", "das Restaurant"):
        assert w in html
    assert html.count("🐢") == 30 * 2 + 10 * 2
    r = client.get("/admin/tts-check/url/", {"text": "das Öl", "lang": "de", "voice": "male"})
    assert r.json()["url"] and google[-1][1]["voice"]["name"] == "de-DE-Neural2-H"
