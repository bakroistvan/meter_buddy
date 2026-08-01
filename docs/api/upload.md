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

Firmware only advances its sync cursor on HTTP **200** or **201** after a batch that included readings.

## Request body

Unknown fields are rejected (`extra = forbid` on the backend). Empty `readings` are allowed (heartbeat / error-only upload).

Firmware may omit optional keys entirely (not send `null`). When more than one POST is needed in a single upload wake (batches of ≤48 readings), top-level `battery_v` / `battery_pct_est` are included only on the **first** `sendBatch` of that session; follow-up truncated batches omit those keys.

```json
{
  "device_id": "meter-buddy-001",
  "meter_impulses_per_kwh": 1000,
  "upload_trigger": "button",
  "battery_v": 3.870,
  "battery_pct_est": 62,
  "readings": [
    {
      "timestamp": "2026-05-01T13:00:00Z",
      "period_start": "2026-05-01T12:00:00Z",
      "pulses": 42
    }
  ],
  "errors": [
    { "code": "no_data", "message": "no unsynced readings" },
    { "code": "crc_mismatch", "message": "record CRC failed", "detail": "offset=64" }
  ]
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `device_id` | string | yes | 1–80 chars |
| `meter_impulses_per_kwh` | int | yes | Must be `> 0` |
| `upload_trigger` | string \| null | no | Firmware currently sends `"button"`; max 40 chars |
| `battery_v` | float \| null | no | Top-level live sample; volts; `>= 0` if present. Firmware serializes with **3 decimal places** (`String(volts, 3)` in `buildBody`). Firmware may omit the key. On a real upload wake, filled from one `battery::sampleForRecord()` (Wi‑Fi forced off + settle) shared with the pre-upload roll, and only on the first POST of that multi-batch session; diagnostics `dump` preview uses immediate `sample()` |
| `battery_pct_est` | int \| null | no | Top-level estimate; 0–100 if present (same sample as `battery_v`). Firmware may omit the key with `battery_v` |
| `readings` | array | yes (may be empty) | List of period records |
| `errors` | array | no (default `[]`) | Device-side issues discovered while building the batch |

### Reading object

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `timestamp` | ISO-8601 datetime | yes | Period end (UTC `Z` from firmware) |
| `period_start` | ISO-8601 datetime \| null | no | Period start |
| `pulses` | int | yes | `>= 0` |
| `battery_v` | float \| null | no | Accepted by the backend if present; current firmware does **not** emit per-reading battery (roll-time mV stays in local `ReadingRecord.batteryMv` only) |
| `battery_pct_est` | int \| null | no | Accepted by the backend if present; current firmware does **not** emit this key on readings |

### Error object

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `code` | string | yes | Stable machine code (see below) |
| `message` | string | yes | Short human-readable text |
| `detail` | string \| null | no | Extra context (e.g. byte offset) |

Stable `code` values from firmware:

| Code | Meaning |
| --- | --- |
| `no_data` | Zero unsynced readings after roll |
| `crc_mismatch` | Bad CRC while scanning `/records.bin` (`detail` includes offset) |
| `storage_unavailable` | LittleFS/storage not ready |
| `batch_truncated` | More unsynced records than one upload batch |

Errors are stored in the dump `raw_json` (no dedicated SQL table in v1).

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
| `stored_readings` | int | Number of readings persisted (`0` for empty heartbeats) |

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

Dump list / meta battery fields are read with `json_extract` on top-level `raw_json` (`$.battery_v` / `$.battery_pct_est`). The HTML index formats `battery_v` with three decimal places in the dump list, chart panel, and telemetry readout. `store_upload` persists `raw_json` via `model_dump(..., exclude_none=True)` so omitted optional keys stay omitted in stored JSON.

## Firmware configuration

Set in `include/local_config.h` (or example defaults):

- `UploadUrl` — full URL ending in `/api/meter-buddy/upload`
- `BasicAuthUser` / `BasicAuthPassword` — must match backend env

## Firmware body builder

`upload::buildBody(batch, batteryReading)` / `sendBatch(batch, batteryReading)` in `include/upload.h` / `src/upload.cpp` take `const battery::Reading*`. When non-null, top-level `battery_v` / `battery_pct_est` are emitted (`battery_v` via `String(volts, 3)` — three decimal places); when `nullptr`, those keys are omitted. Readings serialize as `timestamp` / `period_start` / `pulses` only.

On a real upload wake, firmware calls `sampleForRecord()` once, uses that mV for `rollCurrentPeriod`, and passes `&reading` only to the first `sendBatch` of the session (`includeBattery`); follow-up truncated batches pass `nullptr`. The diagnostics REPL command `d` / `dump…` also uses `buildBody`, with `battery::sample()` passed for top-level fields — same encoder, without forcing Wi‑Fi off / settle, and without rolling or opening the network.
