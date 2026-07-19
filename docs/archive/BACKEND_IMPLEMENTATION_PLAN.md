# FastAPI Backend Implementation Plan

## Goal

Create a proof-of-concept FastAPI backend that receives Meter Buddy upload payloads, authenticates them with HTTP Basic Auth, stores the results in SQLite, and exposes a minimal browser index page where each received upload dump can be downloaded as a file.

## Scope

- Backend framework: FastAPI.
- POC database: SQLite.
- Server runtime: Uvicorn.
- Storage model: preserve the full uploaded JSON dump and also store key metadata for listing/searching.
- UI: very basic HTML index page with one download link per stored dump.
- Download format: JSON file containing the original uploaded payload.
- Auth: HTTP Basic Auth on the ingest endpoint.
- Local development first; production deployment can be documented later.

## Proposed File Layout

```text
backend/
  app/
    __init__.py
    main.py
    auth.py
    database.py
    models.py
    schemas.py
    templates/
      index.html
  requirements.txt
  README.md
  data/
    .gitkeep
```

## API Design

### `POST /api/meter-buddy/upload`

Receives the firmware JSON payload.

Authentication:

- HTTP Basic Auth.
- Username and password loaded from environment variables.

Request body shape:

```json
{
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
}
```

Response on success:

```json
{
  "ok": true,
  "dump_id": 1,
  "stored_readings": 1
}
```

Expected status codes:

- `201 Created` for accepted uploads.
- `401 Unauthorized` for missing or invalid Basic Auth.
- `422 Unprocessable Entity` for invalid JSON shape.

### `GET /`

Returns a minimal HTML index page listing stored dumps.

Each row should show:

- dump id,
- device id,
- upload timestamp,
- number of readings,
- battery voltage,
- battery percentage,
- download link.

### `GET /dumps/{dump_id}.json`

Downloads the original uploaded JSON payload as a file.

Headers:

- `Content-Type: application/json`
- `Content-Disposition: attachment; filename="meter-buddy-dump-{dump_id}.json"`

Return `404` when the dump does not exist.

## SQLite Schema

Use two tables for the POC.

### `upload_dumps`

Stores one row per firmware upload.

Columns:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `received_at TEXT NOT NULL`
- `device_id TEXT NOT NULL`
- `meter_impulses_per_kwh INTEGER NOT NULL`
- `upload_trigger TEXT`
- `battery_v REAL`
- `battery_pct_est INTEGER`
- `reading_count INTEGER NOT NULL`
- `raw_json TEXT NOT NULL`

### `meter_readings`

Stores individual readings for later querying.

Columns:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `dump_id INTEGER NOT NULL REFERENCES upload_dumps(id) ON DELETE CASCADE`
- `device_id TEXT NOT NULL`
- `timestamp TEXT NOT NULL`
- `period_start TEXT`
- `pulses INTEGER NOT NULL`

Indexes:

- `idx_upload_dumps_received_at`
- `idx_meter_readings_device_timestamp`
- `idx_meter_readings_dump_id`

## Configuration

Use environment variables:

- `METER_BUDDY_DB_PATH`
  - Default: `backend/data/meter_buddy.sqlite3`
- `METER_BUDDY_AUTH_USER`
  - Default for local POC: `meter-buddy`
- `METER_BUDDY_AUTH_PASSWORD`
  - Required in non-development deployment.

For the POC, allow a documented local default password, but keep it obvious that production must override it.

## Implementation Steps

1. Create the `backend/` directory structure.
2. Add `requirements.txt` with:
   - `fastapi`
   - `uvicorn[standard]`
   - `jinja2`
   - `pydantic`
3. Implement database initialization in `database.py`.
   - Open SQLite connection.
   - Enable foreign keys.
   - Create tables and indexes on startup.
4. Define Pydantic request schemas in `schemas.py`.
   - Validate upload metadata.
   - Validate readings list.
   - Allow unknown fields only if we want forward compatibility; otherwise reject them.
5. Implement Basic Auth in `auth.py`.
   - Use `secrets.compare_digest`.
   - Return proper `WWW-Authenticate: Basic` header on failure.
6. Implement ingest route in `main.py`.
   - Validate request.
   - Store raw JSON.
   - Insert dump metadata.
   - Insert each reading.
   - Return `201`.
7. Implement index route.
   - Query recent dumps ordered by newest first.
   - Render `templates/index.html`.
8. Implement dump download route.
   - Fetch raw JSON by id.
   - Return as an attachment.
9. Add backend README.
   - Setup commands.
   - Run command.
   - Example `curl` upload.
   - How to configure firmware `UploadUrl`.
10. Add basic verification.
   - Start server locally.
   - POST a sample payload.
   - Open `/`.
   - Download the created JSON dump.

## Ubuntu Run Commands

```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
export METER_BUDDY_AUTH_USER='meter-buddy'
export METER_BUDDY_AUTH_PASSWORD='change-me'
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Firmware development upload URL:

```text
https://your-public-host.example/api/meter-buddy/upload
```

Local-only browser URL:

```text
http://127.0.0.1:8000/
```

## POC Limitations

- SQLite is fine for local/small deployments but should be replaced or backed up carefully for long-running public use.
- Basic Auth is acceptable for this simple ingest endpoint only when served over HTTPS.
- The index page is intentionally plain and not a full dashboard.
- No user management, charts, retention policy, or admin tools in the first pass.

## Acceptance Criteria

- FastAPI server starts with one command.
- `POST /api/meter-buddy/upload` accepts the firmware payload with valid Basic Auth.
- Upload metadata and individual readings are stored in SQLite.
- `GET /` lists stored dumps.
- Each listed dump has a working `.json` download link.
- Invalid credentials return `401`.
- Invalid payloads return `422`.
