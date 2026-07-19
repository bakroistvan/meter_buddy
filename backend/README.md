# Meter Buddy Backend

FastAPI proof-of-concept backend for receiving Meter Buddy upload payloads, storing them in SQLite, and exposing a basic index page with JSON dump downloads.

## Setup

```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## Run

```bash
export METER_BUDDY_AUTH_USER='meter-buddy'
export METER_BUDDY_AUTH_PASSWORD='change-me'
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

## Running with Docker / Docker Compose

You can build and run the backend using Docker Compose from the root directory:

```bash
docker compose up --build -d
```

This starts the FastAPI backend on port `8000` (i.e. `http://127.0.0.1:8000/`). The SQLite database is stored in a persistent Docker volume named `backend_data`.

To run tests inside the Docker container:

```bash
docker compose run --entrypoint "python -m pytest tests" backend
```

## Configuration

Environment variables:

- `METER_BUDDY_DB_PATH`
  - Default: `backend/data/meter_buddy.sqlite3`
- `METER_BUDDY_AUTH_USER`
  - Default: `meter-buddy`
- `METER_BUDDY_AUTH_PASSWORD`
  - Default: `change-me`

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
