#!/bin/sh
set -eu

python << 'PY'
import os
import sys
import time

import psycopg

host = os.environ.get("POSTGRES_HOST", "db")
port = os.environ.get("POSTGRES_PORT", "5432")
name = os.environ.get("POSTGRES_DB", "auslagen")
user = os.environ.get("POSTGRES_USER", "auslagen")
password = os.environ.get("POSTGRES_PASSWORD", "")

last_error = None
for _ in range(30):
    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname=name,
            user=user,
            password=password,
        ) as connection:
            connection.execute("SELECT 1")
        break
    except Exception as exc:  # noqa: BLE001 - retry until Postgres accepts connections
        last_error = exc
        time.sleep(1)
else:
    print(f"Datenbank nicht erreichbar: {last_error}", file=sys.stderr)
    sys.exit(1)
PY

echo "Datenbank ist erreichbar. Migrationen laufen."
python manage.py migrate --noinput
echo "Stammdaten werden angelegt."
python manage.py seed_masterdata
exec "$@"
