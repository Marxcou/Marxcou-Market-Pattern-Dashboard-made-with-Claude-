#!/bin/sh
# Updates the server to the state of main: back up, pull, build, restart, check.
# Usage in the project folder: ./deploy/update.sh
set -eu
cd "$(dirname "$0")/.."
. ./deploy/lib.sh
echo "1/4 Backup ..."
if [ -x deploy/backup.sh ] && $COMPOSE ps --status running api 2>/dev/null | grep -q api; then
  ./deploy/backup.sh || echo "Warning: backup failed, continuing anyway."
fi
echo "2/4 Fetching latest state ..."
git pull --ff-only
echo "3/4 Building and starting ..."
$COMPOSE up -d --build
echo "4/4 Waiting for api ..."
i=0
until [ "$($COMPOSE ps --format '{{.Health}}' api 2>/dev/null)" = "healthy" ]; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { echo "api did not become healthy. Log: $COMPOSE logs api --tail 50" >&2; exit 1; }
  sleep 5
done
docker image prune -f >/dev/null
echo "Done. State: $(git rev-parse --short HEAD)"
