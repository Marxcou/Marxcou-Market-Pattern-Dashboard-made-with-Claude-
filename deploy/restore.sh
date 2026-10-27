#!/bin/sh
# Restores a backup. Usage: ./deploy/restore.sh /opt/marktmuster-backups/marktmuster-XXXX.db.gz
# The current database is first set aside in the volume as marktmuster.db.vor-restore.
set -eu
[ $# -eq 1 ] && [ -f "$1" ] || { echo "Usage: $0 <backup.db.gz>" >&2; exit 1; }
cd "$(dirname "$0")/.."
. ./deploy/lib.sh
printf 'The current database will be replaced. Continue? (yes/no) '
read -r answer
[ "$answer" = "yes" ] || { echo "Aborted."; exit 1; }
$COMPOSE stop worker api
gunzip -c "$1" | $COMPOSE run --rm --no-deps -T api sh -c '
  cp /data/marktmuster.db /data/marktmuster.db.vor-restore 2>/dev/null || true
  rm -f /data/marktmuster.db-wal /data/marktmuster.db-shm
  cat > /data/marktmuster.db'
$COMPOSE up -d api worker
echo "Restored from $1."
