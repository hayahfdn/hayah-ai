#!/usr/bin/env bash
# Pull the latest code from GitHub (main) and rebuild only when something changed.
set -euo pipefail
exec 9>/run/hayah-update.lock
flock -n 9 || exit 0
cd /opt/hayah
git fetch -q origin main
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]; then exit 0; fi
echo "Updating $(git rev-parse --short HEAD) -> $(git rev-parse --short origin/main)"
/usr/local/bin/hayah-backup || true   # a backup before every update
git reset -q --hard origin/main
install -m 755 deploy/update.sh /usr/local/bin/hayah-update
install -m 755 deploy/backup.sh /usr/local/bin/hayah-backup
docker compose -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --build --remove-orphans
docker image prune -f >/dev/null
