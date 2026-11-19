#!/bin/sh
set -e

# Wait for the database (Postgres in docker compose / Render).
python - <<'PY'
import os, sys, time
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.db import connection
for attempt in range(60):
    try:
        connection.ensure_connection()
        break
    except Exception as exc:  # noqa: BLE001
        print(f"Waiting for database... ({exc.__class__.__name__})", flush=True)
        time.sleep(1)
else:
    sys.exit("Database not reachable")
PY

python manage.py migrate --noinput
python manage.py seed_words
python manage.py ensure_superuser
python manage.py collectstatic --noinput -v 0

exec "$@"
