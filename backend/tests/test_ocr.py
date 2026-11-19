import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from ocr.models import ScanLog
from ocr.schema import ExtractionError, parse_json_text, validate_payload
from ocr.services import extract_with_llm, heuristic_parse


def png_bytes(size=(50, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


GOOD = {
    "language": "de",
    "pairs": [
        {
            "word": "der Bahnhof",
            "definition": "Ort für Züge",
            "part_of_speech": "noun",
            "article": None,
            "translation_uz": "vokzal",
        },
        {
            "word": "schnell",
            "definition": "mit hoher Geschwindigkeit",
            "part_of_speech": "adjective",
            "article": "der",
            "translation_uz": "tez",
        },
        {"word": "", "definition": "skip me", "part_of_speech": "", "article": None, "translation_uz": ""},
    ],
}


def test_validate_payload_normalises():
    out = validate_payload(GOOD)
    assert out["language"] == "de"
    assert len(out["pairs"]) == 2
    assert out["pairs"][0]["word"] == "Bahnhof" and out["pairs"][0]["article"] == "der"


def test_english_never_gets_articles():
    out = validate_payload(
        {
            "language": "en",
            "pairs": [
                {
                    "word": "dog",
                    "definition": "an animal",
                    "part_of_speech": "noun",
                    "article": "der",
                    "translation_uz": "it",
                }
            ],
        }
    )
    assert out["pairs"][0]["article"] is None


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {"language": "fr", "pairs": []},
        {"language": "en"},
        {"language": "en", "pairs": "x"},
        {"language": "en", "pairs": [1]},
    ],
)
def test_validate_payload_rejects(bad):
    with pytest.raises(ExtractionError):
        validate_payload(bad)


def test_parse_json_text_handles_fences_and_prose():
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Here you go: {"a": 2} thanks') == {"a": 2}
    with pytest.raises(ExtractionError):
        parse_json_text("no json here")
    with pytest.raises(ExtractionError):
        parse_json_text("{broken")


def test_llm_retries_once_on_invalid_json():
    calls = []

    def caller(img, mt):
        calls.append(1)
        return "not json" if len(calls) == 1 else json.dumps(GOOD)

    out = extract_with_llm(b"x", "image/jpeg", caller=caller)
    assert len(calls) == 2
    assert len(out["pairs"]) == 2


def test_llm_gives_up_after_retry():
    calls = []

    def caller(img, mt):
        calls.append(1)
        return "{bad"

    with pytest.raises(ExtractionError):
        extract_with_llm(b"x", "image/jpeg", caller=caller)
    assert len(calls) == 2


def test_heuristic_parser():
    text = "1. abundant - existing in large amounts\nreluctant: (adj) not willing\nPage 12\n"
    out = heuristic_parse(text, "en")
    assert [p["word"] for p in out["pairs"]] == ["abundant", "reluctant"]
    assert out["pairs"][1]["part_of_speech"] == "adj"


@pytest.mark.django_db
def test_scan_endpoint_mock_mode(api, settings):
    settings.OCR_MOCK = True
    r = api.post(
        "/api/ocr/scan/",
        {"image": SimpleUploadedFile("p.png", png_bytes(), "image/png"), "track": "de"},
        format="multipart",
    )
    assert r.status_code == 200, r.data
    assert r.data["engine"] == "mock" and r.data["language"] == "de"
    assert all(p["translation_uz"] for p in r.data["pairs"])
    assert "first_scan" in r.data["new_achievements"]
    assert ScanLog.objects.count() == 1


@pytest.mark.django_db
def test_scan_rate_limit(api, settings, user):
    settings.OCR_MOCK = True
    settings.OCR_DAILY_LIMIT = 2
    for _ in range(2):
        ScanLog.objects.create(user=user)
    r = api.post("/api/ocr/scan/", {"image": SimpleUploadedFile("p.png", png_bytes(), "image/png")}, format="multipart")
    assert r.status_code == 429


@pytest.mark.django_db
def test_scan_size_limit(api, settings):
    settings.OCR_MOCK = True
    settings.MAX_UPLOAD_BYTES = 100
    r = api.post(
        "/api/ocr/scan/", {"image": SimpleUploadedFile("p.png", png_bytes((300, 300)), "image/png")}, format="multipart"
    )
    assert r.status_code == 413


@pytest.mark.django_db
def test_scan_rejects_non_image(api, settings):
    settings.OCR_MOCK = True
    r = api.post(
        "/api/ocr/scan/", {"image": SimpleUploadedFile("p.png", b"not an image", "image/png")}, format="multipart"
    )
    assert r.status_code == 422
