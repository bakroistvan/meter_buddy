# Meter Buddy Backend

FastAPI proof-of-concept backend for receiving Meter Buddy upload payloads, storing them in SQLite, and exposing a basic index page with JSON dump downloads.

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
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Setup

```bash
cd backend
python3 -m venv .venv
# Windows: python -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
# Windows: .\.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
cd backend
$env:METER_BUDDY_AUTH_USER="meter-buddy"
$env:METER_BUDDY_AUTH_PASSWORD="change-me"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

## Running with Docker / Docker Compose

From the **`backend/`** directory:

```bash
cd backend
docker compose up --build -d
```

This starts the FastAPI backend on port `8000` (`http://127.0.0.1:8000/`). The SQLite database is stored in a persistent Docker volume named `backend_data`.

`docker-compose.yml` injects auth credentials at **runtime** (local defaults `meter-buddy` / `change-me`). Override the password for anything beyond local use, for example:

```bash
METER_BUDDY_AUTH_PASSWORD='your-secret' docker compose up --build -d
```

Or edit the Compose `environment` / use an `env_file` that is not committed.

To run a pre-built image (e.g. from GHCR) without Compose:

```bash
docker run --rm -p 8000:8000 \
  -e METER_BUDDY_AUTH_USER=meter-buddy \
  -e METER_BUDDY_AUTH_PASSWORD='your-secret' \
  -e METER_BUDDY_DB_PATH=/data/meter_buddy.sqlite3 \
  -v meter_buddy_data:/data \
  ghcr.io/<owner>/meter_buddy:latest
```

The Dockerfile does **not** bake `METER_BUDDY_AUTH_USER` or `METER_BUDDY_AUTH_PASSWORD` into the image. In CI/production, set them from GitHub Secrets, orchestrator secrets, or `docker -e` — never via image `ENV`/`ARG`.

To run tests inside the Docker container:

```bash
cd backend
docker compose run --entrypoint "python -m pytest tests" backend
```

## Configuration

Environment variables:

- `METER_BUDDY_DB_PATH`
  - Default: `backend/data/meter_buddy.sqlite3` (relative to the backend package when unset); Docker image default `/data/meter_buddy.sqlite3`
- `METER_BUDDY_AUTH_USER`
  - App fallback when unset: `meter-buddy`
  - Inject at runtime for Docker/deployed runs (not set in the Dockerfile)
- `METER_BUDDY_AUTH_PASSWORD`
  - App fallback when unset: `change-me` (local/dev only)
  - **Inject at runtime for Docker/deployed runs** — pass via Compose, `docker -e`, or secrets; not set in the Dockerfile

Use a real password and HTTPS for anything reachable outside your machine.

## Example Upload

```bash
curl -i \
  -u 'meter-buddy:change-me' \
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
  http://127.0.0.1:8000/api/meter-buddy/upload
```

## Test

```bash
cd backend
./.venv/bin/python -m pytest tests
```

## Firmware URL

For local LAN testing through a tunnel or reverse proxy, configure firmware `UploadUrl` to:

```text
https://your-public-host.example/api/meter-buddy/upload
```
