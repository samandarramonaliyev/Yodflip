import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_register_login_me():
    c = APIClient()
    r = c.post("/api/auth/register/", {"email": "Bob@Example.com", "password": "secret123"}, format="json")
    assert r.status_code == 201
    assert r.data["user"]["email"] == "bob@example.com"
    assert r.data["access"] and r.data["refresh"]

    r = c.post("/api/auth/login/", {"email": "bob@example.com", "password": "secret123"}, format="json")
    assert r.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    me = c.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["display_name"] == "bob"
    assert me.data["active_track"] == "en"
    assert me.data["ui_language"] == "uz"


def test_register_duplicate_email(user):
    r = APIClient().post("/api/auth/register/", {"email": "ALI@example.com", "password": "secret123"}, format="json")
    assert r.status_code == 400


def test_login_wrong_password(user):
    r = APIClient().post("/api/auth/login/", {"email": "ali@example.com", "password": "nope"}, format="json")
    assert r.status_code == 401


def test_me_requires_auth():
    assert APIClient().get("/api/auth/me/").status_code == 401


def test_patch_track_and_language(api):
    r = api.patch("/api/auth/me/", {"active_track": "de", "ui_language": "ru"}, format="json")
    assert r.status_code == 200
    assert r.data["active_track"] == "de"
    assert r.data["ui_language"] == "ru"
    # xp is read-only
    r = api.patch("/api/auth/me/", {"xp": 99999}, format="json")
    assert r.data["xp"] == 0


def test_refresh_token(user):
    c = APIClient()
    r = c.post("/api/auth/login/", {"email": "ali@example.com", "password": "secret123"}, format="json")
    r2 = c.post("/api/auth/refresh/", {"refresh": r.data["refresh"]}, format="json")
    assert r2.status_code == 200 and r2.data["access"]
