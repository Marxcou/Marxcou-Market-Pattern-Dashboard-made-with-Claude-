#!/bin/sh
# Sets up the nightly backup (03:15 server time). Run once as root.
set -eu
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cat > /etc/cron.d/marktmuster-backup <<CRON
15 3 * * * root cd $DIR && ./deploy/backup.sh >> /var/log/marktmuster-backup.log 2>&1
CRON
chmod 644 /etc/cron.d/marktmuster-backup
echo "Nightly backup set up (log: /var/log/marktmuster-backup.log)."
