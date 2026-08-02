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
├── Caddyfile             # Let's Encrypt reverse proxy
├── docker-compose.yml
├── Dockerfile
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

## Running with Docker / Docker Compose (HTTPS + Let’s Encrypt)

**Requirements:** a public DNS name (`A`/`AAAA`) pointing at this host, and inbound TCP **80** + **443** for ACME HTTP-01.

From **`backend/`**:

```bash
export METER_BUDDY_DOMAIN=meter.example.com
export METER_BUDDY_AUTH_USER=meter-buddy
export METER_BUDDY_AUTH_PASSWORD='your-strong-secret'
docker compose up --build -d
```

Compose starts:

- **Caddy** on host ports 80/443 — automatic Let’s Encrypt certificate for `$METER_BUDDY_DOMAIN`, reverse-proxies to the backend
- **backend** — internal only (no published `8000`); non-root image; `read_only` + dropped capabilities

The app refuses to start if `METER_BUDDY_AUTH_PASSWORD` is missing or still `change-me` (Compose does not set `METER_BUDDY_ALLOW_INSECURE_AUTH`).

UI: `https://$METER_BUDDY_DOMAIN/` (Basic Auth). Upload: `https://$METER_BUDDY_DOMAIN/api/meter-buddy/upload`.

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

1. Deploy Compose as above; confirm `https://$METER_BUDDY_DOMAIN/` prompts for Basic Auth.
2. In `include/local_config.h` (from `config.example.h`):
   - `UploadUrl = "https://<domain>/api/meter-buddy/upload"`
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
- `METER_BUDDY_DOMAIN` — public hostname for Caddy Let’s Encrypt (Compose)

All HTTP routes and `/ws` require Basic Auth except `/healthz`.

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
  https://meter.example.com/api/meter-buddy/upload
```

## Test

```bash
# From backend/ (needs requirements-dev.txt)
./.venv/bin/python -m pytest tests

# Or from repo root:
python -m pip install -r backend/requirements-dev.txt
python -m pytest -q backend
```
