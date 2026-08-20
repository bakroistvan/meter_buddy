# Migration: HTTP LAN → HTTPS (DuckDNS + port 9111)

Checklist for a home server behind a router: DuckDNS name, one forwarded HTTPS port, Let’s Encrypt via **DNS-01** (no WAN port 80).

## What changes

| Before | After |
| --- | --- |
| Host port `8000` published | HTTPS on host **9111** (configurable); plain HTTP on **9111** 308s to HTTPS (same port) |
| HTTP | HTTPS + Let’s Encrypt (DuckDNS DNS-01) |
| Only upload required Basic Auth | **All** routes + `/ws` require Basic Auth (`/healthz` excepted) |
| Password may be `change-me` | Strong password **required** |
| Firmware `http://…:8000` + `AllowInsecureTls` | `https://….duckdns.org:9111/…` + `TlsCaCert = IsrgRootCerts` |

Existing SQLite in the `backend_data` Docker volume is kept if you reuse the same Compose project/volume name.

---

## 0. Decide inputs

- [ ] **DuckDNS subdomain**: create at [duckdns.org](https://www.duckdns.org/) → e.g. `changeme.duckdns.org`
- [ ] **DuckDNS token** (account page): `________________`
- [ ] Point DuckDNS at your current public IP (site “update IP” / their client)
- [ ] **Auth username**: `________________` (default `meter-buddy`)
- [ ] **Strong auth password** (not `change-me`): `________________`
- [ ] **Router port forward**: WAN TCP **9111** → LAN IP of the Docker host, port **9111**
- [ ] Host firewall allows inbound TCP **9111** (if enabled)

No need to forward 80 or 443.

---

## 1. Preserve data (if upgrading an old Compose stack)

On the server, from `backend/`:

```bash
docker compose down
docker volume ls | grep backend_data
```

- [ ] Do **not** use `docker compose down -v` (wipes DB)
- [ ] Optional backup while old `:8000` stack still runs:

```bash
curl -o meter_buddy_backup.sqlite3 http://127.0.0.1:8000/db
```

---

## 2. Prefer image deploy (compose + `.env`)

**Recommended:** follow [deploy/README.md](../deploy/README.md) — only `deploy/docker-compose.yml` and a filled `.env` on the host (pulls GHCR images). No repo clone.

**Source build alternative:** clone the repo so `backend/` includes `Dockerfile`, `Dockerfile.caddy`, `docker-compose.yml`, `Caddyfile`, `.env.example`, then use the steps below from `backend/`.

---

## 3. Create `.env`

**Image deploy** (from the directory with `deploy/docker-compose.yml`):

```bash
cp .env.example .env
```

**Source build** (from `backend/`):

```bash
cd backend
cp .env.example .env
```

Edit `.env`:

```env
METER_BUDDY_DOMAIN=changeme.duckdns.org
DUCKDNS_TOKEN=your-duckdns-token
METER_BUDDY_HTTPS_PORT=9111
METER_BUDDY_AUTH_USER=meter-buddy
METER_BUDDY_AUTH_PASSWORD=your-strong-secret
METER_BUDDY_DB_PATH=/data/meter_buddy.sqlite3
```

- [ ] Domain matches your DuckDNS name
- [ ] Token is correct (not empty)
- [ ] Password is not `change-me`
- [ ] Do not set `METER_BUDDY_ALLOW_INSECURE_AUTH`
- [ ] Never commit `.env`

---

## 4. Start stack

**Image deploy:**

```bash
docker compose up -d
docker compose ps
docker compose logs -f caddy
```

**Source build** (from `backend/`):

```bash
cd backend
docker compose up --build -d
docker compose ps
docker compose logs -f caddy
```

First source build compiles Caddy with the DuckDNS plugin (slow once). Image deploy pulls pre-built images instead.

- [ ] Both services running
- [ ] Caddy log shows certificate obtained (DNS-01; may take 1–2 minutes)
- [ ] From the internet (phone LTE, not LAN Wi‑Fi):  
  `https://changeme.duckdns.org:9111/healthz` → `{"ok":true}`
- [ ] Browser prompts for Basic Auth on `https://changeme.duckdns.org:9111/`
- [ ] Prior dumps still visible (volume reused)

If ACME fails: wrong `DUCKDNS_TOKEN`, domain typo, or DuckDNS IP not updated. Port forward does **not** need to be up for DNS-01 (only for serving HTTPS afterward).

---

## 5. Retire old HTTP `:8000`

- [ ] Nothing still publishes host `:8000` for Meter Buddy
- [ ] Bookmarks / scripts → `https://changeme.duckdns.org:9111`
- [ ] `sync_db_from_remote.py` with HTTPS + `--password`

```bash
python script/sync_db_from_remote.py \
  --remote "https://changeme.duckdns.org:9111" \
  --local "http://127.0.0.1:8000" \
  --user meter-buddy \
  --password 'your-strong-secret'
```

---

## 6. Firmware

In `include/local_config.h`:

- [ ] `#include "certs/isrg_roots.h"`
- [ ] `UploadUrl = "https://changeme.duckdns.org:9111/api/meter-buddy/upload"`
- [ ] `FirmwareVersionUrl` same host/port if used
- [ ] Basic Auth matches `.env`
- [ ] `TlsCaCert = IsrgRootCerts`
- [ ] `AllowInsecureTls = false`
- [ ] Build and flash; short-press upload succeeds

---

## 7. Ongoing

- [ ] Keep DuckDNS IP updated if your WAN IP changes
- [ ] Rotate password in `.env` + `docker compose up -d` + firmware Basic Auth
- [ ] Leaf cert renewals are automatic (DNS-01); no firmware change

---

## Rollback

1. `docker compose down` (in the deploy directory or `backend/`)
2. Temporarily run old `:8000` / local uvicorn with `METER_BUDDY_ALLOW_INSECURE_AUTH=1` on LAN only
3. Point firmware back at `http://…` only for that window
4. Keep `backend_data` volume unless you intentionally wipe it

---

## Quick verify

```bash
# From the directory that has docker-compose.yml and .env
set -a && source .env && set +a

curl -fsS "https://${METER_BUDDY_DOMAIN}:${METER_BUDDY_HTTPS_PORT}/healthz"

curl -i -u "${METER_BUDDY_AUTH_USER}:${METER_BUDDY_AUTH_PASSWORD}" \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"meter-buddy-001","meter_impulses_per_kwh":1000,"upload_trigger":"button","readings":[]}' \
  "https://${METER_BUDDY_DOMAIN}:${METER_BUDDY_HTTPS_PORT}/api/meter-buddy/upload"

curl -o /dev/null -w "%{http_code}\n" \
  "https://${METER_BUDDY_DOMAIN}:${METER_BUDDY_HTTPS_PORT}/"
# expect 401
```
