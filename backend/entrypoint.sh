#!/bin/sh
# Container start: wait for the DB, migrate, seed (only if the seed changed), ensure the admin user.
set -e

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
        time.sleep(2)
else:
    sys.exit("Database not reachable")
PY

python manage.py migrate --noinput
python manage.py seed_words          # idempotent: skipped when this seed version is already loaded
python manage.py seed_exams          # exam packs, idempotent as well
python manage.py ensure_superuser    # only if DJANGO_SUPERUSER_EMAIL/PASSWORD are set and the user is missing
if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput -v 0
fi

exec "$@"
