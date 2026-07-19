# Upload API contract

Shared contract between ESP32 firmware (`src/upload.cpp`) and the backend (`POST /api/meter-buddy/upload`).

## Endpoint

| Item | Value |
| --- | --- |
| Method | `POST` |
| Path | `/api/meter-buddy/upload` |
| Auth | HTTP Basic (`METER_BUDDY_AUTH_USER` / `METER_BUDDY_AUTH_PASSWORD`) |
| Content-Type | `application/json` |
| Success | `201 Created` (also treat `200` as success on the device) |

Firmware only advances its sync cursor on HTTP **200** or **201**.

## Request body

Unknown fields are rejected (`extra = forbid` on the backend).

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

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `device_id` | string | yes | 1–80 chars |
| `meter_impulses_per_kwh` | int | yes | Must be `> 0` |
| `upload_trigger` | string \| null | no | Firmware currently sends `"button"`; max 40 chars |
| `battery_v` | float \| null | no | Volts; must be `>= 0` if present |
| `battery_pct_est` | int \| null | no | 0–100 if present |
| `readings` | array | yes (may be empty) | List of period records |

### Reading object

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `timestamp` | ISO-8601 datetime | yes | Period end (UTC `Z` from firmware) |
| `period_start` | ISO-8601 datetime \| null | no | Period start |
| `pulses` | int | yes | `>= 0` |

## Success response

```json
{
  "ok": true,
  "dump_id": 1,
  "stored_readings": 1
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `ok` | bool | Always `true` on success |
| `dump_id` | int | SQLite `upload_dumps.id` |
| `stored_readings` | int | Number of readings persisted |

## Error responses

| Status | When |
| --- | --- |
| `401` | Missing/invalid Basic Auth |
| `422` | Validation failure (missing fields, bad types, extra keys) |

## Related endpoints (backend UI / clients)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | none | HTML index of dumps |
| `GET` | `/dumps/{id}/preview` | none | Raw dump JSON inline |
| `GET` | `/dumps/{id}.json` | none | Dump JSON as download |
| `WS` | `/ws` | none | Push `{ "type": "new_dump", "dump": {…meta} }` |

## Firmware configuration

Set in `include/local_config.h` (or example defaults):

- `UploadUrl` — full URL ending in `/api/meter-buddy/upload`
- `BasicAuthUser` / `BasicAuthPassword` — must match backend env
