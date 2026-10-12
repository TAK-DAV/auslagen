#!/bin/sh
# Daily backup of PostgreSQL and media files.
# Intended to run on the Lightsail host via cron, then copy off-box (S3).
#
# Required env (from /etc/auslagen-backup.env or the project .env):
#   POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
#   BACKUP_DIR   local directory on the server (default /var/backups/auslagen)
# Optional:
#   S3_BACKUP_URI  e.g. s3://tak-auslagen-backups/daily/
#   AWS_DEFAULT_REGION  e.g. eu-central-1
#   RETAIN_DAYS  default 30

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
PROJECT_DIR="${PROJECT_DIR:-/opt/auslagen}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/auslagen}"
RETAIN_DAYS="${RETAIN_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

cd "$PROJECT_DIR"

mkdir -p "$BACKUP_DIR/db" "$BACKUP_DIR/media"

echo "Dumping database…"
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > "$BACKUP_DIR/db/auslagen-${STAMP}.dump"

echo "Archiving media volume…"
MEDIA_CID="$(docker compose -f "$COMPOSE_FILE" ps -q web)"
docker run --rm --volumes-from "$MEDIA_CID" \
  -v "$BACKUP_DIR/media:/backup" alpine:3.20 \
  tar -czf "/backup/media-${STAMP}.tar.gz" -C /app/media .

echo "Pruning local backups older than ${RETAIN_DAYS} days…"
find "$BACKUP_DIR/db" -type f -mtime "+${RETAIN_DAYS}" -delete
find "$BACKUP_DIR/media" -type f -mtime "+${RETAIN_DAYS}" -delete

if [ -n "${S3_BACKUP_URI:-}" ]; then
  echo "Uploading to ${S3_BACKUP_URI}…"
  aws s3 cp "$BACKUP_DIR/db/auslagen-${STAMP}.dump" "${S3_BACKUP_URI%/}/db/"
  aws s3 cp "$BACKUP_DIR/media/media-${STAMP}.tar.gz" "${S3_BACKUP_URI%/}/media/"
fi

echo "Backup finished: ${STAMP}"
