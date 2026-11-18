# Deployment guide

Target: one small Linux VPS (2 vCPU, 4 GB RAM, 80 GB disk is enough to start;
~$10–25/month). **Nothing is purchased by the code; HAYAH approves and buys the
VPS.** The same steps work on any Linux machine with Docker.

## 1. Server

```bash
# Ubuntu 24.04
curl -fsSL https://get.docker.com | sh
git clone <HAYAH repo> hayah-ai && cd hayah-ai
cp .env.example .env
openssl rand -hex 32   # paste as HAYAH_JWT_SECRET
openssl rand -hex 16   # paste as POSTGRES_PASSWORD
```

Set `HAYAH_ENV=production` and `HAYAH_CORS_ORIGINS=https://<your domain>`.

## 2. HTTPS

Point a subdomain (e.g. `ops.hayah.org`) at the server and put Caddy or
Cloudflare in front of port 8080. Caddy example (`/etc/caddy/Caddyfile`):

```
ops.hayah.org {
  reverse_proxy localhost:8080
}
```

## 3. Start

```bash
docker compose up -d --build
docker compose exec api python -m app.cli create-admin --email <admin email> --name "<name>"
```

## 4. Google Sheets and Drive (HAYAH business Google account)

1. In HAYAH's Google Cloud project, enable **Google Sheets API** and **Google Drive API**.
2. Create an OAuth client ("Desktop app"), save it as `secrets/google-oauth-client.json`.
3. On a computer with a browser: `python scripts/google_oauth.py` and sign in with the HAYAH account.
   Copy `secrets/google-oauth-token.json` to the server's `secrets/`.
4. On the same computer, from `backend/`:
   `HAYAH_SHEETS_BACKEND=google HAYAH_DRIVE_BACKEND=google HAYAH_SECRETS_DIR=../secrets python ../scripts/check_google.py`.
   It creates the spreadsheet tabs and the `HAYAH PROJECTS` folders (no project data) and prints their ids.
5. On the server set `HAYAH_SHEETS_BACKEND=google`, `HAYAH_DRIVE_BACKEND=google` and the two printed ids in `.env`,
   then `docker compose up -d`.

The Google APIs are free for this volume. Drive storage counts against the account's quota
(the dashboard shows usage and the daily health check warns above 85%).

## 5. WhatsApp intake number (Phase 5)

See docs/WHATSAPP.md. Webhook URL: `https://ops.hayah.org/webhooks/whatsapp`.

## 6. Backups

```bash
docker compose --profile backup run --rm backup     # ./backups/hayah-YYYYMMDD-HHMM.dump
```

Run it daily from cron and copy `./backups` off the server (for example to the
HAYAH Google Drive). Remove old dumps by hand when you no longer need them.
Restore: `pg_restore -h <host> -U hayah -d hayah --clean <file>.dump`.

## 7. Updating

```bash
git pull && docker compose up -d --build     # migrations run automatically on start
```
