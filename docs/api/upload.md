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

Firmware may omit optional keys entirely (not send `null`). When more than one POST is needed in a single upload wake (batches of **128** readings, `config::MaxUploadRecords`), top-level `battery_v` / `battery_pct_est` are included only on the **first** `HttpSession::post` of that session; follow-up truncated batches omit those keys. `errors[]` is capped at `config::MaxUploadErrors` = **8**.

```json
{
  "device_id": "meter-buddy-001",
  "meter_impulses_per_kwh": 1000,
  "upload_trigger": "button",
  "battery_v": 3.775,
  "battery_pct_est": 50,
  "readings": [
    {
      "timestamp": "2026-05-01T13:00:00Z",
      "period_start": "2026-05-01T12:00:00Z",
      "pulses": 42,
      "battery_v": 3.775,
      "battery_pct_est": 50
    }
  ],
  "errors": [
    { "code": "no_data", "message": "no unsynced readings" },
    { "code": "crc_mismatch", "message": "record CRC failed", "detail": "offset=64" },
    { "code": "low_battery", "message": "protection lock from low battery" },
    { "code": "brownout_lock", "message": "protection lock from brown-out reset" }
  ]
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `device_id` | string | yes | 1–80 chars |
| `meter_impulses_per_kwh` | int | yes | Must be `> 0` |
| `upload_trigger` | string \| null | no | Firmware currently sends `"button"`; max 40 chars |
| `battery_v` | float \| null | no | Top-level live sample; volts; `>= 0` if present. Firmware serializes with **3 decimal places** (`snprintf` `%.3f` in `buildBody`). Firmware may omit the key. On a real upload wake, filled from one `battery::sampleForRecord()` (Wi‑Fi forced off + settle) shared with the pre-upload roll, and only on the first POST of that multi-batch session; diagnostics `dump` preview uses immediate `sample()` |
| `battery_pct_est` | int \| null | no | Top-level estimate; 0–100 if present (same sample as `battery_v`). Firmware may omit the key with `battery_v`. Mapping is `battery::estimatePercent` (board-calibrated piecewise ADC-volt table: **≥ 4.05 V** rest after ETA4054 CV → 100%, **≤ 3.26 V** empty-cliff → 0%; loaded charge peaks ~4.12–4.18 V also clamp at 100%; not textbook 4.20/3.30 — see [fw_specification.md](../firmware/fw_specification.md) Battery ADC). Independent of protection hysteresis (`BatteryRadioBlockVolts` 3.30 / `BatteryRadioUnlockVolts` 3.50): 3.30 V is ~1% SoC, not 0%; 3.50 V is ~6% |
| `readings` | array | yes (may be empty) | List of period records. Firmware includes at most `config::MaxUploadRecords` = **128** per POST |
| `errors` | array | no (default `[]`) | Device-side issues discovered while building the batch. Firmware includes at most `config::MaxUploadErrors` = **8** entries |

### Reading object

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `timestamp` | ISO-8601 datetime | yes | Period end (UTC `Z` from firmware) |
| `period_start` | ISO-8601 datetime \| null | no | Period start |
| `pulses` | int | yes | `>= 0` |
| `battery_v` | float \| null | no | Volts from stored `ReadingRecord.batteryMv / 1000`; firmware always emits this on each reading, serialized with **3 decimal places** (`snprintf` `%.3f`). Backend still accepts omitted keys (clients that omit them stay omitted) |
| `battery_pct_est` | int \| null | no | 0–100 estimate recomputed via `battery::estimatePercent` from that same voltage; percent is **not** stored on disk. Firmware always emits this on each reading. Same board-calibrated piecewise ADC-volt table as top-level (**≥ 4.05 V** → 100%, **≤ 3.26 V** → 0%; interpolate between knots; firmware rounds to nearest int). Same independence from protection hysteresis as the top-level field |

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
| `batch_truncated` | More unsynced records than one upload batch (`config::MaxUploadRecords` = **128**) |
| `low_battery` | Protection lock was latched because pack voltage was below `BatteryRadioBlockVolts` (default **3.30**; firmware message: `protection lock from low battery`). Pending in `/brownout.dat` until attached on a POST that receives HTTP 200/201 (including an empty heartbeat). Not the same threshold as SoC 0% (empty-cliff **3.26 V**) |
| `brownout_lock` | Protection lock was latched because last reset was `ESP_RST_BROWNOUT` (firmware message: `protection lock from brown-out reset`). Same pending/clear lifecycle as `low_battery`; both may appear together |

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

Every backend route requires HTTP Basic Auth (`METER_BUDDY_AUTH_USER` / `METER_BUDDY_AUTH_PASSWORD`) except `GET /healthz`. OpenAPI (`/docs`, `/redoc`, `/openapi.json`) is disabled unless `METER_BUDDY_ENABLE_DOCS=1`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/meter-buddy/upload` | Basic | Device ingest (this contract) |
| `GET` | `/healthz` | none | Liveness (Docker/Caddy health) |
| `GET` | `/` | Basic | HTML index of dumps |
| `GET` | `/dumps` | Basic | Dump list meta JSON |
| `GET` | `/dumps/{id}/preview` | Basic | Raw dump JSON inline |
| `GET` | `/dumps/{id}.json` | Basic | Dump JSON as download |
| `DELETE` | `/dumps` / `/dumps/{id}` | Basic | Delete dumps |
| `GET`/`POST`/`DELETE` | `/db` | Basic | Download / replace / reset SQLite |
| `WS` | `/ws` | Basic | Push `{ "type": "new_dump", "dump": {…meta} }` |

Dump list / meta battery fields are read with `json_extract` on top-level `raw_json` (`$.battery_v` / `$.battery_pct_est`). The HTML index formats `battery_v` with three decimal places in the dump list, chart panel, and telemetry readout. When a reading lacks `battery_pct_est`, the lifetime calculator recomputes SoC from `battery_v` via `estimatePercentFromVolts` (same knots as firmware `kOcv`; see [fw_specification.md](../firmware/fw_specification.md) Battery ADC). `store_upload` persists `raw_json` via `model_dump(..., exclude_none=True)` so omitted optional keys stay omitted in stored JSON.

## Firmware configuration

Set in `include/local_config.h` (or example defaults):

- `UploadUrl` — full HTTPS URL ending in `/api/meter-buddy/upload`
- `BasicAuthUser` / `BasicAuthPassword` — must match backend env
- `TlsCaCert` — default `IsrgRootCerts` from `include/certs/isrg_roots.h` (ISRG Root X1 + X2); do not pin the rotating Let’s Encrypt leaf. Set `AllowInsecureTls = false` for production HTTPS.

## Firmware body builder

`upload::buildBody(batch, batteryReading)` in `include/upload.h` / `src/upload.cpp` takes `const battery::Reading*`. When non-null, top-level `battery_v` / `battery_pct_est` are emitted (`battery_v` via `snprintf` `%.3f` — three decimal places); when `nullptr`, those keys are omitted. Timestamps are ISO-8601 UTC `Z` via `appendIso8601` (`strftime` into a stack buffer). Readings serialize as `timestamp` / `period_start` / `pulses` / `battery_v` / `battery_pct_est` (`battery_v` from `record.batteryMv / 1000.0f` at 3 decimal places; `battery_pct_est` from `battery::estimatePercent` of that voltage). Field names and types are unchanged. Pending `low_battery` / `brownout_lock` are attached by `storage::attachPendingProtectionErrors` before POST and included in `errors[]`; they clear only after HTTP 200/201.

The upload wake POSTs through one `upload::HttpSession` (HTTP keep-alive; TLS `WiFiClientSecure` only when `UploadUrl` is `https://`; `end()` before OTA). `sendBatch(batch, batteryReading)` is a one-shot wrapper that constructs its own `HttpSession` and calls `post`. On a real upload wake, firmware calls `sampleForRecord()` once, uses that mV for `rollCurrentPeriod`, and passes `&reading` only to the first `HttpSession::post` of the session (`includeBattery`); follow-up truncated batches pass `nullptr`. The diagnostics REPL command `d` / `dump…` also uses `buildBody`, with `battery::sample()` passed for top-level fields — same encoder, without forcing Wi‑Fi off / settle, and without rolling or opening the network.
