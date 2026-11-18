#!/usr/bin/env bash
# Database backup to /opt/hayah/backups, keeping the last 14 days.
set -euo pipefail
cd /opt/hayah
mkdir -p backups
f=backups/hayah-$(date +%Y%m%d-%H%M).dump
docker compose -f docker-compose.yml -f deploy/docker-compose.server.yml exec -T db pg_dump -U hayah -Fc hayah > "$f.tmp"
mv "$f.tmp" "$f"
find backups -name 'hayah-*.dump' -mtime +14 -delete
