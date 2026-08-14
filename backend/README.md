# Meter Buddy Backend

FastAPI backend for receiving Meter Buddy upload payloads, storing them in SQLite, and exposing an authenticated index page with JSON dump downloads.

Upload contract: [docs/api/upload.md](../docs/api/upload.md).

## Layout

```text
backend/
├── app/
│   ├── main.py           # FastAPI app wiring
│   ├── api/              # HTTP/WebSocket routes
│   ├── core/             # auth
│   ├── db/               # SQLite access
│   ├── schemas/          # Pydantic models
│   ├── services/         # WebSocket broadcast
│   └── templates/
├── tests/
├── data/                 # local SQLite (gitignored content)
├── Caddyfile             # Let's Encrypt (DuckDNS DNS-01) reverse proxy
├── docker-compose.yml
├── Dockerfile            # FastAPI backend
├── Dockerfile.caddy      # Caddy + caddy-dns/duckdns
├── .env.example          # copy to .env for Compose
├── requirements.txt      # runtime
└── requirements-dev.txt  # runtime + pytest/httpx
```

## Setup

```bash
cd backend
python3 -m venv .venv
# Windows: python -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
# Windows: .\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

## Run (local, no Docker)

Local uvicorn allows the default password only with `METER_BUDDY_ALLOW_INSECURE_AUTH=1`:

```powershell
cd backend
$env:METER_BUDDY_AUTH_USER="meter-buddy"
$env:METER_BUDDY_AUTH_PASSWORD="change-me"
$env:METER_BUDDY_ALLOW_INSECURE_AUTH="1"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` (browser prompts for Basic Auth). Liveness: `GET /healthz` (no auth).

## Running with Docker / Docker Compose (HTTPS + DuckDNS)

Step-by-step cutover: [MIGRATION_HTTPS.md](MIGRATION_HTTPS.md).

**Typical home setup:** DuckDNS name (e.g. `changeme.duckdns.org`) → your public IP; router port-forwards **WAN TCP 9111 → LAN host:9111**. Certs use **Let’s Encrypt DNS-01** via your DuckDNS token — **port 80 is not required**.

From **`backend/`**:

```bash
cp .env.example .env
# Edit .env:
#   METER_BUDDY_DOMAIN=changeme.duckdns.org
#   DUCKDNS_TOKEN=...          # from https://www.duckdns.org/
#   METER_BUDDY_HTTPS_PORT=9111
#   METER_BUDDY_AUTH_USER / METER_BUDDY_AUTH_PASSWORD
docker compose up --build -d
```

First `caddy` build compiles Caddy with the DuckDNS plugin (can take a few minutes).

Compose starts:

- **Caddy** — HTTPS on host `METER_BUDDY_HTTPS_PORT` (default 9111); ACME via DuckDNS DNS-01
- **backend** — Compose network only; non-root; `read_only` + dropped capabilities

UI: `https://changeme.duckdns.org:9111/` (Basic Auth).  
Upload: `https://changeme.duckdns.org:9111/api/meter-buddy/upload`.  
Firmware OTA (device): `https://changeme.duckdns.org:9111/api/meter-buddy/firmware/version` — see [docs/api/firmware.md](../docs/api/firmware.md).  
GitHub release mirror token: [GITHUB_TOKEN.md](GITHUB_TOKEN.md).

There is no public HTTP redirect (port 80 not published). Always use `https://…:9111`.

To run a pre-built image behind your own TLS proxy:

```bash
docker run --rm \
  -e METER_BUDDY_AUTH_USER=meter-buddy \
  -e METER_BUDDY_AUTH_PASSWORD='your-secret' \
  -e METER_BUDDY_DB_PATH=/data/meter_buddy.sqlite3 \
  -v meter_buddy_data:/data \
  ghcr.io/<owner>/meter_buddy:latest
```

The Dockerfile does **not** bake auth credentials into the image.

## HTTPS (Let’s Encrypt) + firmware TLS

Leaf certificates renew automatically via Caddy. Firmware must pin the **ISRG roots**, not the leaf.

1. Deploy Compose as above; confirm `https://changeme.duckdns.org:9111/` prompts for Basic Auth.
2. In `include/local_config.h` (from `config.example.h`):
   - `UploadUrl = "https://changeme.duckdns.org:9111/api/meter-buddy/upload"`
   - `FirmwareVersionUrl = "https://changeme.duckdns.org:9111/api/meter-buddy/firmware/version"`
   - Matching `BasicAuthUser` / `BasicAuthPassword`
   - `#include "certs/isrg_roots.h"` and `TlsCaCert = IsrgRootCerts` (vendored X1 + X2)
   - `AllowInsecureTls = false`
3. Rebuild/flash firmware.

Routine Let’s Encrypt renewals need **no** firmware change. Root updates are rare; maintainers refresh with:

```bash
python script/refresh_isrg_roots.py
```

Sources: https://letsencrypt.org/certs/isrgrootx1.pem and https://letsencrypt.org/certs/isrg-root-x2.pem — index at https://letsencrypt.org/certificates/

## Configuration

Environment variables:

- `METER_BUDDY_DB_PATH` — default `backend/data/meter_buddy.sqlite3` locally; Docker `/data/meter_buddy.sqlite3`
- `METER_BUDDY_AUTH_USER` — default `meter-buddy`
- `METER_BUDDY_AUTH_PASSWORD` — required strong secret in production; default `change-me` only with `METER_BUDDY_ALLOW_INSECURE_AUTH=1`
- `METER_BUDDY_ALLOW_INSECURE_AUTH` — `1` for local/tests only (never in Compose)
- `METER_BUDDY_ENABLE_DOCS` — `1` to expose `/docs` / OpenAPI (off by default)
- `METER_BUDDY_DOMAIN` — DuckDNS hostname (e.g. `changeme.duckdns.org`)
- `DUCKDNS_TOKEN` — DuckDNS API token for Let’s Encrypt DNS-01
- `METER_BUDDY_HTTPS_PORT` — host HTTPS port (default `9111`; router forwards this port)
- `METER_BUDDY_GITHUB_REPO` — GitHub `owner/repo` to mirror (default `bakroistvan/meter_buddy`)
- `METER_BUDDY_GITHUB_TOKEN` — optional fine-grained PAT; see [GITHUB_TOKEN.md](GITHUB_TOKEN.md)
- `METER_BUDDY_FIRMWARE_DIR` — mirrored `.bin` + `manifest.json` (Docker default `/data/firmware`)
- `METER_BUDDY_FIRMWARE_SYNC_INTERVAL_SEC` — poll interval (default `86400` = 1 day); startup always syncs once
- `METER_BUDDY_FIRMWARE_DISABLE_SYNC` — `1` to skip background poll (tests)

All HTTP routes and `/ws` require Basic Auth except `/healthz`.

### Firmware mirror endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/meter-buddy/firmware/version` | Device OTA (`HTTPUpdate`: `304` / `200` `.bin` + `x-MD5` / `503` if cache empty) — not a JSON document |
| `GET` | `/api/meter-buddy/firmware` | Operator: mirrored tags, md5, last sync status |
| `POST` | `/api/meter-buddy/firmware/sync` | Operator: pull GitHub Releases now (`502` on sync failure) |

Contract: [docs/api/firmware.md](../docs/api/firmware.md). Token setup: [GITHUB_TOKEN.md](GITHUB_TOKEN.md).

## Example Upload

```bash
curl -i \
  -u 'meter-buddy:your-strong-secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "device_id": "meter-buddy-001",
    "meter_impulses_per_kwh": 1000,
    "upload_trigger": "button",
    "battery_v": 3.87,
    "battery_pct_est": 62,
    "readings": [
      {
        "timestamp": "2026-05-01T13:00:00Z",
        "period_start": "2026-05-01T12:00:00Z",
        "pulses": 42
      }
    ]
  }' \
  https://changeme.duckdns.org:9111/api/meter-buddy/upload
```

## Test

```bash
# From backend/ (needs requirements-dev.txt)
./.venv/bin/python -m pytest tests

# Or from repo root:
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q backend
```

Firmware unit tests mock GitHub. To exercise a real Releases download (latest `meter-buddy-fw-v*.bin`):

```powershell
$env:METER_BUDDY_LIVE_GITHUB="1"
# Optional: $env:METER_BUDDY_GITHUB_TOKEN="github_pat_..."
.\.venv\Scripts\python -m pytest -q tests/test_firmware.py -m live_github
```

Without `METER_BUDDY_LIVE_GITHUB=1`, the live test is skipped.