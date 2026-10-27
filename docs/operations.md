# Running on a server

For continuous operation on a rented server (recommended: Hetzner CX23, Ubuntu 24.04, Docker). The step-by-step guide from renting the server to the first login is in the project's server guide; this document describes what exists in the repository for it and how to operate the server.

**Secrets:** API keys, `SESSION_SECRET` and `ADMIN_PASSWORD` only live in the `.env` on the server (`chmod 600`). They are never in the repository, never in an image and never in logs (see `backend/app/log_redaction.py`). With `APP_ENV=production` the API does not start while `SESSION_SECRET` (at least 32 characters) or `ADMIN_PASSWORD` still has the example value.

## Two operating modes

| | Option A: Tailscale | Option B: public address with HTTPS |
|---|---|---|
| Reachable for | Devices in the private Tailscale network | Anyone with the address (login required) |
| Start | `docker compose up -d --build` | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` |
| Address | `http://<Tailscale IP>:8080` | `https://<DOMAIN>` |
| `.env` | `COOKIE_SECURE=false`, `DOMAIN` empty | `COOKIE_SECURE=true`, `DOMAIN=mydashboard.example` |
| Firewall | SSH (22) only | SSH (22), 80, 443 |

The scripts in `deploy/` detect the mode themselves: if `DOMAIN` is set in `.env`, they use the production file (`deploy/lib.sh`).

### Option B in detail

1. Point the domain's A record at the server IP and open ports 80 and 443 in the firewall.
2. In `.env`: `APP_ENV=production`, `COOKIE_SECURE=true`, `DOMAIN=...`, a new `SESSION_SECRET`, a strong `ADMIN_PASSWORD`.
3. Start as in the table. Caddy (`deploy/Caddyfile`) obtains and renews the certificate itself (Let's Encrypt), redirects HTTP to HTTPS and sets security headers (HSTS, `nosniff`, `X-Frame-Options`, `Referrer-Policy`). Certificates live in the volume `caddy_data` so they survive restarts.
4. In this mode the app has no host port; only Caddy is reachable from outside.

**Cookies and CSRF:** The session cookie is `HttpOnly`, `SameSite=Lax` and, with `COOKIE_SECURE=true`, only valid over HTTPS. Every modifying request additionally needs the CSRF token in the header `X-CSRF-Token` (`backend/app/deps.py`). Without HTTPS (option A) `COOKIE_SECURE=false` must stay, otherwise login is impossible.

**Caution, Docker and the firewall:** Docker bypasses `ufw`. Rely on the provider's firewall (Hetzner), not on `ufw`.

## Updating

```bash
cd /opt/marktmuster
./deploy/update.sh
```

The script backs up the database, fetches `main` (`git pull --ff-only`), rebuilds, restarts, waits for a healthy API and cleans up old images. Database migrations run automatically when the API starts (`alembic upgrade head`). If `git pull` aborts because files were changed on the server, do not overwrite anything there; look at the change instead.

## Backup

- **Nightly:** `sudo ./deploy/install-cron.sh` sets up a cron entry once (03:15 server time). `deploy/backup.sh` uses the SQLite backup function to create a consistent copy (even while running), compresses it to `/opt/marktmuster-backups/marktmuster-<timestamp>.db.gz` (readable by `root` only) and deletes backups older than 14 days (`BACKUP_KEEP_DAYS`, `BACKUP_DIR` can be changed). Log: `/var/log/marktmuster-backup.log`.
- **Manual:** `./deploy/backup.sh`
- **Check:** `ls -lh /opt/marktmuster-backups/` (a new file every night, plausible size)
- **Restore:** `./deploy/restore.sh /opt/marktmuster-backups/marktmuster-XXXX.db.gz`. The script asks for confirmation, stops API and worker, puts the old database aside as `marktmuster.db.vor-restore` in the volume, restores the backup and restarts.
- The backup contains accounts (password hashes), watchlists, news and analyses, but **not** the `.env`. Keep the `.env` separately and safe (for example in a password manager).
- In addition, Hetzner backups cover the whole server. Backups on the same server do not protect against its loss: now and then copy one to your own PC, for example `scp root@<server>:/opt/marktmuster-backups/marktmuster-XXXX.db.gz .`

## Day to day

| Task | Command (in the project folder) |
|---|---|
| Status | `docker compose ps` |
| API log | `docker compose logs api --tail 100` |
| Pattern backtest (one-off, takes a while) | `docker compose run --rm worker python -m app.backtest_job` |
| Restart | `docker compose restart` |
| Memory, disk space | `free -h`, `df -h`, `docker system df` |

With option B, add the options `-f docker-compose.yml -f docker-compose.prod.yml` before every `docker compose` command.

All services start by themselves after a server reboot (`restart: unless-stopped`).

## Before inviting friends

Check the terms of use of the free data tiers (Alpaca, Finnhub, Marketaux, RSS feeds); the Claude budget (`CLAUDE_MONTHLY_BUDGET_USD`) applies to all users together. The notice "does not constitute investment advice" appears on every page.
