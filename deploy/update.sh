#!/bin/sh
# Pull the latest release and rebuild the production stack.
# Run as the deploy user from /opt/auslagen.

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
PROJECT_DIR="${PROJECT_DIR:-/opt/auslagen}"

cd "$PROJECT_DIR"

echo "1/4 Pull from GitHub…"
git pull --ff-only

echo "2/4 Rebuild and restart…"
docker compose -f "$COMPOSE_FILE" up -d --build

echo "3/4 Collect static files…"
docker compose -f "$COMPOSE_FILE" exec -T web python manage.py collectstatic --noinput

echo "4/4 Smoke check…"
docker compose -f "$COMPOSE_FILE" ps
curl -fsS -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/" || true

echo "Update finished."
