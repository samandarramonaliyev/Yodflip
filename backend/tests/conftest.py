import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import User


@pytest.fixture
def seeded(db):
    call_command("seed_words", verbosity=0)


@pytest.fixture
def user(db):
    return User.objects.create_user(email="ali@example.com", password="secret123", display_name="Ali")


@pytest.fixture
def client_for():
    def make(u):
        c = APIClient()
        c.force_authenticate(u)
        return c

    return make


@pytest.fixture
def api(user, client_for):
    return client_for(user)
