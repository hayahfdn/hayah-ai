#!/usr/bin/env bash
# HAYAH AI – one-time server setup for a fresh Ubuntu 24.04 server.
# Run as root (the Hetzner "Cloud config" box does this automatically):
#   curl -fsSL https://raw.githubusercontent.com/hayahfdn/hayah-ai/main/deploy/install.sh | bash
# The first admin comes from /root/hayah-admin.env (ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD).
# Safe to run again: it keeps the existing .env, data and users.
set -euo pipefail
exec > >(tee -a /var/log/hayah-install.log) 2>&1
echo "== HAYAH install started $(date -Is)"

APP=/opt/hayah
REPO=${HAYAH_REPO:-https://github.com/hayahfdn/hayah-ai.git}
export DEBIAN_FRONTEND=noninteractive

# 1. Packages and firewall (only SSH and the website are open).
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git ufw curl ca-certificates
systemctl enable --now docker
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

# 2. A little swap so builds never run out of memory.
if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 3. Code.
if [ ! -d "$APP/.git" ]; then git clone --depth 50 "$REPO" "$APP"; fi
cd "$APP"
mkdir -p secrets backups

# 4. Settings with fresh random secrets (created once, never overwritten).
IP=$(curl -fsS --max-time 5 http://169.254.169.254/hetzner/v1/metadata/public-ipv4 2>/dev/null \
     || ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
DOMAIN=${HAYAH_DOMAIN:-$(echo "$IP" | tr . -).sslip.io}
if [ ! -f .env ]; then
  umask 077
  cat > .env <<ENV
POSTGRES_PASSWORD=$(openssl rand -hex 24)
WEB_PORT=127.0.0.1:8080
HAYAH_DOMAIN=$DOMAIN
HAYAH_ENV=production
HAYAH_JWT_SECRET=$(openssl rand -hex 32)
HAYAH_CORS_ORIGINS=https://$DOMAIN
HAYAH_SHEETS_BACKEND=mock
HAYAH_DRIVE_BACKEND=mock
HAYAH_WHATSAPP_BACKEND=mock
HAYAH_AI_BACKEND=rules
ENV
  umask 022
fi
DOMAIN=$(grep '^HAYAH_DOMAIN=' .env | cut -d= -f2)

# 5. Start everything (database, API, worker, dashboard, HTTPS).
COMPOSE="docker compose -f docker-compose.yml -f deploy/docker-compose.server.yml"
$COMPOSE up -d --build
for i in $(seq 1 60); do
  $COMPOSE exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" 2>/dev/null && break
  sleep 5
done

# 6. First admin.
if [ -f /root/hayah-admin.env ]; then
  set -a; . /root/hayah-admin.env; set +a
  $COMPOSE exec -T -e ADMIN_PASSWORD api python -m app.cli create-admin \
    --email "$ADMIN_EMAIL" --name "${ADMIN_NAME:-Admin}" --password-env ADMIN_PASSWORD
  shred -u /root/hayah-admin.env || rm -f /root/hayah-admin.env
fi

# 7. Auto-update from GitHub every 5 minutes, and a nightly backup at 02:30.
install -m 755 deploy/update.sh /usr/local/bin/hayah-update
install -m 755 deploy/backup.sh /usr/local/bin/hayah-backup
cat > /etc/systemd/system/hayah-update.service <<UNIT
[Unit]
Description=HAYAH AI: pull new code from GitHub and rebuild
After=docker.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/hayah-update
UNIT
cat > /etc/systemd/system/hayah-update.timer <<UNIT
[Unit]
Description=HAYAH AI auto-update every 5 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
cat > /etc/systemd/system/hayah-backup.service <<UNIT
[Unit]
Description=HAYAH AI: nightly database backup
After=docker.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/hayah-backup
UNIT
cat > /etc/systemd/system/hayah-backup.timer <<UNIT
[Unit]
Description=HAYAH AI nightly backup
[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now hayah-update.timer hayah-backup.timer

echo "https://$DOMAIN" > /root/HAYAH-URL.txt
echo "== HAYAH install finished $(date -Is). Open https://$DOMAIN"
