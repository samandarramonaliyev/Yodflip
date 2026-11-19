import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD if missing."

    def handle(self, *args, **opts):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not email or not password:
            self.stdout.write("Superuser env vars not set; skipping.")
            return
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write("Superuser exists.")
            return
        User.objects.create_superuser(email=email.lower(), password=password, display_name="Admin")
        self.stdout.write(self.style.SUCCESS(f"Superuser {email} created."))
