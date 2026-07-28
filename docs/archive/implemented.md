# Meter Buddy — Implemented System

Battery-powered ESP32-C3 firmware for counting electricity meter LED pulses and uploading stored readings on demand. Includes a FastAPI backend for receiving and viewing uploads.

---

## Hardware Target

| Component | Part | Role |
|-----------|------|------|
| MCU + Radio | Seeed Studio XIAO ESP32-C3 | Pulse interrupts, I2C, ADC, deep sleep, Wi-Fi STA, HTTPS POST |
| RTC + EEPROM | DS3231 + AT24C32 breakout | Absolute timekeeping, 4 KB non-volatile storage |
| Light sensor | TEMT6000 breakout | Detect electricity meter pulse LED flashes |
| Battery | KXD 383450PL LiPo 3.7 V 650 mAh | Primary energy reservoir (~1.5-2 years) |
| Charger | TP4056 (RPROG → 3 kΩ, 400 mA) | Safe LiPo charging via USB |
| Button | Momentary push button (NO) | Manual upload trigger |

---

## Pin Map (from `include/pins.h`)

| Function | XIAO pin | GPIO | Notes |
|----------|----------|------|-------|
| Battery ADC | D0 / A0 | GPIO2 | 1:2 external divider (200 kΩ + 200 kΩ) |
| Unused | D1 | GPIO3 | Intentionally unconnected |
| Pulse wake | D2 | GPIO4 | TEMT6000 OUT, RISING edge deep-sleep wake |
| RTC alarm wake | D3 | GPIO5 | DS3231 SQW/INT, active LOW deep-sleep wake |
| I2C SDA | D4 | GPIO6 | DS3231 + AT24C32 |
| I2C SCL | D5 | GPIO7 | DS3231 + AT24C32 |
| Upload button | D6 | GPIO21 | `INPUT_PULLUP`, active LOW — **polled only** (cannot wake from deep sleep on ESP32-C3) |
| Debug LED | D7 | GPIO20 | On when awake, off when sleeping |

**Deep sleep GPIO wake** on ESP32-C3 is limited to GPIOs 0–5. The upload button (GPIO21) is polled during `setup()` and in `loop()`.

---

## Wiring

### Power Network

```
KXD LiPo 650 mAh 3.7 V
  ├─ (+) ─┬─ TP4056 B+
  │       └─ XIAO BAT+ pad (underside)
  └─ (–) ─┬─ TP4056 B–
          └─ XIAO GND pad (underside)

XIAO 3.3V ─── DS3231 VCC, TEMT6000 VCC
All GNDs common
```

### Data Signals

| Connection | XIAO | Peripheral |
|------------|------|------------|
| I2C data | D4 (GPIO6) | DS3231 SDA / AT24C32 SDA |
| I2C clock | D5 (GPIO7) | DS3231 SCL / AT24C32 SCL |
| Pulse interrupt | D2 (GPIO4) | TEMT6000 OUT |
| RTC alarm | D3 (GPIO5) | DS3231 SQW/INT |
| Upload button | D6 (GPIO21) | Button → GND |
| Battery divider | A0/D0 (GPIO2) | Midpoint of 200 kΩ + 200 kΩ |

### Battery Voltage Divider

```
BAT+ ─── R1 200 kΩ ───┬─── A0 / D0 (GPIO2)
                       │
                      R2 200 kΩ
                       │
                      GND
```

- Ratio: 1:2 (multiply ADC reading by 2)
- Use 1% tolerance resistors (200 kΩ each; 220 kΩ acceptable)
- D0 is a strapping pin; divider output sits at ~1.85 V at boot (above LOW threshold)

### TP4056 Charger Modification

- Desolder the 1.2 kΩ RPROG resistor
- Replace with **3 kΩ** resistor (sets charge current to ~400 mA)
- Input: USB 5 V

---

## **TEMT6000 must be powered from 3.3V, not a GPIO pin.** The earlier design connected VCC to D1 (GPIO3) for switched power, but this prevents deep-sleep wake on pulse. Always-on 3.3V power ensures the sensor can wake the MCU via the pulse interrupt line.

---

## Configuration (compile-time)

Defaults in `include/config.example.h`. For real credentials, create `include/local_config.h` (gitignored) with the same `config` namespace values.

| Setting | Default | Purpose |
|---------|---------|---------|
| `DeviceId` | `meter-buddy-001` | Identifies this logger |
| `MeterImpulsesPerKwh` | 1000 | Meter constant, included in upload JSON |
| `WifiSsid` / `WifiPassword` | — | iPhone Personal Hotspot credentials |
| `UploadUrl` | `https://example.com/api/meter-buddy/upload` | HTTPS POST endpoint |
| `BasicAuthUser` / `BasicAuthPassword` | `meter-buddy` / `change-me` | HTTP Basic Auth credentials |
| `TlsCaCert` | empty | Server CA cert in PEM format |
| `AllowInsecureTls` | `false` | Skip TLS verification (dev only) |
| `NtpServer1` / `NtpServer2` | `pool.ntp.org` / `time.google.com` | NTP servers for time sync |
| `PulseDebounceMs` | 50 | ISR edge filter (ms) |
| `PulseAwakeThresholdMs` | 8000 | Gap threshold: isolated vs burst (ms) |
| `PulseAwakeQuietMs` | 30000 | End-of-burst quiet timeout (ms) |
| `PulseAwakeMaxMs` | 300000 | Hard cap on burst counting (ms) |
| `AwakePulseFlushMs` | 5000 | Burst→EEPROM flush interval (ms) |
| `WifiReconnectIntervalMs` | 10000 | WiFi reconnect check interval (ms) |
| `WifiConnectTimeoutMs` | 30000 | Max Wi-Fi join wait (ms) |
| `HttpTimeoutMs` | 20000 | HTTP POST timeout (ms) |
| `NtpSyncTimeoutMs` | 10000 | NTP sync timeout (ms) |
| `RtcWakeIntervalMinutes` | 1440 (24 h) | DS3231 alarm interval |
| `EnableDeepSleep` | `true` | Enter deep sleep after each wake cycle |
| `KeepWifiConnectedWhenAwake` | `false` | Maintain Wi-Fi connection in awake mode |
| `StayAwakeOnUsbBoot` | `true` | Stay awake when powered via USB |
| `EnableSerialLogs` | `true` | Enable serial debug output |

---

## Software Stack

| Layer | Choice |
|-------|--------|
| Language | C++ (Arduino framework) |
| Build | PlatformIO |
| Board | Seeed Studio XIAO ESP32-C3 |
| Libraries | RTClib, HTTPClient, WiFiClientSecure |
| RTC | DS3231 via I2C |
| Storage | AT24C32 EEPROM via I2C |
| Backend | FastAPI + SQLite + Uvicorn |

---

## Firmware Architecture

### File Layout

```
include/
  pins.h          — GPIO constants
  config.h        — conditional include (local_config.h or config.example.h)
  config.example.h — compile-time defaults
  battery.h       — Reading struct, begin, sample, estimatePercent
  rtc_clock.h     — DS3231 init, nowUnix, adjustUnix, alarm functions
  storage.h       — ReadingRecord, UploadBatch, EEPROM API
  upload.h        — Result enum, sendBatch, ensureWifiConnected
src/
  main.cpp        — Entry point, wake dispatch, ISR, deep sleep orchestration
  battery.cpp     — ADC sampling (16× averaged), voltage→percent mapping
  rtc_clock.cpp   — DS3231 init, nowUnix, adjustUnix, alarm scheduling
  storage.cpp     — AT24C32 header, ring-buffer records, CRC-16 integrity
  upload.cpp      — Wi-Fi connect, NTP sync, HTTPS POST with JSON body
```

### State Machine

```
Deep Sleep ──┬──► Pulse (GPIO4 HIGH) ──► handlePulseWake()
             │       ├─ interval > 8 s → store 1 pulse, sleep
             │       └─ interval ≤ 8 s → countAwakeUntilQuiet()
             │                            ├─ accumulate via ISR
             │                            └─ quiet ≥ 30 s or ≥ 5 min → sleep
             ├──► RTC alarm (GPIO5 LOW) ──► handleRtcWake()
             │       └─ roll period, sample battery, schedule next alarm
             ├──► Button (GPIO21 LOW) ──► handleUploadWake()
             │       └─ debounce, roll period, Wi-Fi + NTP + POST, mark synced
             └──► Cold boot / USB ──► handleDiagnosticsBoot()
                     └─ dump storage, schedule alarm; stay awake if USB
```

### Key Data Types

**`storage::ReadingRecord`** (packed, 18 bytes):

| Offset | Size | Field |
|--------|------|-------|
| 0 | 4 | `sequence` — monotonic ID |
| 4 | 4 | `periodStart` — unix timestamp |
| 8 | 4 | `pulses` — pulse count in this period |
| 12 | 2 | `batteryMv` — end-of-period mV / 1000 |
| 14 | 2 | `flags` — reserved |
| 16 | 2 | `crc` — CRC-16 over preceding 16 bytes |

**`storage::UploadBatch`**: up to 48 records + count + newestSequence.

**`upload::Result`**: `Success`, `NoData`, `WifiFailed`, `HttpFailed`, `ServerRejected`.

**`battery::Reading`**: `volts` (float), `percent` (uint8_t).

### EEPROM Layout (AT24C32, 4 KB)

| Address | Content |
|---------|---------|
| 0 – 63 | Header (magic=`0x4D425544 "MBUD"`, version=1, nextSequence, syncedThrough, currentPeriodStart, currentPulses, crc) |
| 64 – 4095 | Ring-buffer of `ReadingRecord`, 18 bytes each, ~224 slots |

Records wrap at `(4096 - 64) / 18 = 224` slots. Header tracks `nextSequence` for the next record ID and `syncedThrough` for the highest sequence confirmed uploaded.

### CRC-16

Calculated over all fields except the CRC field itself. Used for both header and record integrity.

---

## Wake Scenarios

### Pulse (GPIO4 rising edge)

1. Deep sleep → `setup()` → GPIO4 HIGH → `handlePulseWake()`
2. Re-wake gating via `lastPulseWakeUnix` (RTC_DATA_ATTR) prevents double-counting the same pulse
3. If gap since previous pulse > `PulseAwakeThresholdMs` (8 s): isolated pulse → store 1, sleep
4. If gap ≤ 8 s: burst mode → `countAwakeUntilQuiet()`:
   - Settle: wait up to 200 ms for pin to go LOW
   - Attach RISING ISR with 50 ms debounce
   - Accumulate pulses, polling every 25 ms
   - Exit when quiet for 30 s or 5 min elapsed → store total, sleep

### RTC Alarm (GPIO5 LOW)

1. `handleRtcWake()`: clear alarm, sample battery, roll current period (finalize existing record + start new)
2. `scheduleNextWakeAlarm()`: next midnight (≥ 24 h) or next minute (debug mode)

### Upload Button (GPIO21 LOW — polled only)

1. `handleUploadWake()`: debounce (50 ms), dump storage to serial, roll current period
2. Load unsynced batch (up to 48 records) from EEPROM ring-buffer
3. `upload::sendBatch()`:
   - Wi-Fi STA join (30 s timeout)
   - NTP sync (10 s timeout) → adjust DS3231
   - Build compact JSON body
   - HTTPS POST with Basic Auth
   - HTTP 200/201 → `storage::markSyncedThrough()`
   - Any failure → data preserved for retry
4. Enter deep sleep

### Cold Boot / USB Power

1. `handleDiagnosticsBoot()`: dump storage to serial, sample battery
2. `scheduleNextWakeAlarm()`
3. If `StayAwakeOnUsbBoot` (default true on debug builds): attach pulse ISR, fall through to `loop()`
4. Otherwise: enter deep sleep

### Awake Loop (`loop()`)

When deep sleep is disabled (USB debug mode):

- `flushAwakePulses()` every 5 s: write ISR-accumulated pulses to EEPROM
- `pollAwakeControls()`: check button press, check RTC pin state
- `keepWifiConnected()` every 10 s: reconnect if disconnected

---

## Upload Flow

1. Press D6 button
2. Firmware wakes from deep sleep (or button is polled in awake mode)
3. Debounce (50 ms)
4. Roll current period in EEPROM
5. Load unsynced records from ring-buffer (up to 48)
6. Sample battery voltage (16× averaged, ×2 divider compensation)
7. Join iPhone Personal Hotspot (Wi-Fi STA)
8. Sync system/RTC time from NTP
9. POST compact JSON to HTTPS endpoint with Basic Auth
10. HTTP 200/201 → advance sync cursor; failure → preserve data
11. Radio off → deep sleep

JSON payload shape:

```json
{
  "device_id": "meter-buddy-001",
  "meter_impulses_per_kwh": 1000,
  "upload_trigger": "button",
  "battery_v": 3.87,
  "battery_pct_est": 62,
  "readings": [
    { "timestamp": "2026-05-01T13:00:00Z", "period_start": "2026-05-01T12:00:00Z", "pulses": 42 }
  ]
}
```

---

## Battery Monitoring

- 16 averaged `analogReadMilliVolts(A0)` samples × 2 (divider compensation)
- Sampled on: upload button press, RTC daily wake (optional), diagnostics boot
- **Not sampled on pulse wake** (keep wake time minimal)

| Voltage | Meaning |
|---------|---------|
| 4.15 – 4.20 V | Full |
| 3.70 V | ~50 % |
| 3.40 – 3.50 V | Low — plan recharge |
| ≤ 3.30 V | Critical — recharge soon |

`estimatePercent()` linearly maps 3.30 V → 0 % to 4.20 V → 100 %.

---

## Backend (FastAPI + SQLite)

### File Layout

```
backend/
  app/
    __init__.py
    main.py         — FastAPI app, routes, WebSocket manager
    auth.py         — HTTP Basic Auth via secrets.compare_digest
    database.py     — SQLite connection, schema, CRUD
    schemas.py      — Pydantic models (UploadPayload, MeterReading, UploadResponse)
    templates/
      index.html    — Dump listing with inline preview + WebSocket live updates
  tests/
    conftest.py
    test_app.py     — Integration tests for upload, index, download, auth, WebSocket
  requirements.txt
  data/             — SQLite DB directory (created automatically)
```

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/meter-buddy/upload` | Basic | Receive firmware upload, store in SQLite |
| `GET` | `/` | None | Minimal HTML dump listing with preview toggles |
| `GET` | `/dumps/{id}.json` | None | Download original JSON as attachment |
| `GET` | `/dumps/{id}/preview` | None | Inline JSON preview (no Content-Disposition) |
| `WS` | `/ws` | None | WebSocket for live new-dump notifications |

### SQLite Schema

**`upload_dumps`**: `id`, `received_at`, `device_id`, `meter_impulses_per_kwh`, `upload_trigger`, `battery_v`, `battery_pct_est`, `reading_count`, `raw_json`.

**`meter_readings`**: `id`, `dump_id` (FK → upload_dumps), `device_id`, `timestamp`, `period_start`, `pulses`.

### Configuration (environment variables)

- `METER_BUDDY_DB_PATH` — default: `backend/data/meter_buddy.sqlite3`
- `METER_BUDDY_AUTH_USER` — default: `meter-buddy`
- `METER_BUDDY_AUTH_PASSWORD` — default: `change-me`

### Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
$env:METER_BUDDY_AUTH_USER='meter-buddy'
$env:METER_BUDDY_AUTH_PASSWORD='change-me'
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Test

```bash
cd backend
.venv\Scripts\python -m pytest tests
```

### Example Upload

```bash
curl -i -u 'meter-buddy:change-me' -H 'Content-Type: application/json' \
  -d '{"device_id":"meter-buddy-001","meter_impulses_per_kwh":1000,"upload_trigger":"button","battery_v":3.87,"battery_pct_est":62,"readings":[{"timestamp":"2026-05-01T13:00:00Z","period_start":"2026-05-01T12:00:00Z","pulses":42}]}' \
  http://127.0.0.1:8000/api/meter-buddy/upload
```

---

## Build & Flash

### Prerequisites

- Python 3
- PlatformIO (installed automatically by wrapper)

### Commands

```powershell
.\meter_buddy.bat build         # Build firmware
.\meter_buddy.bat flash         # Flash to device (auto-detect COM)
.\meter_buddy.bat flash --port COM5
.\meter_buddy.bat monitor --port COM5
.\meter_buddy.bat flash-monitor --port COM5
.\meter_buddy.bat upload --port COM5   # Flash alias
```

### Manual

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install platformio
$env:PLATFORMIO_CORE_DIR='.\.platformio-core'
.\.venv\Scripts\python -m platformio run
```

---

## Key Design Decisions

- **No formal state machine class.** Wake-cause dispatch in `setup()` plus `loop()` polling implements the state machine procedurally.
- **Re-wake gating via `lastPulseWakeUnix` (RTC_DATA_ATTR).** Prevents double-counting the same persistent pulse edge.
- **Ring-buffer EEPROM without wear leveling.** ~183 slots, full cycle every ~186 uploads → ~1M+ writes before wear concern on 4 KB AT24C32.
- **Wi-Fi on demand only.** Radio off in deep sleep; turned on only during button-press upload sessions.
- **NTP sync on every upload.** DS3231 drifts between sessions (<2 min/year), so each upload session resyncs.
- **No `models.py` in backend.** Pydantic models live in `schemas.py`; SQLite schema is inline in `database.py`.
- **WebSocket support for live UI updates.** The frontend receives real-time notifications when new dumps arrive.
- **TLS support with optional insecure mode.** Uses `WiFiClientSecure`. Supports CA certificate pinning or `setInsecure()` for development.

---

## Differences from Original Design (`idea.md`)

| Aspect | Original (`idea.md`) | Implemented (code) |
|--------|---------------------|-------------------|
| TEMT6000 VCC | D1 (switched GPIO) | **3.3V always on** (needed for deep-sleep wake) |
| Button wake mechanism | `ext1_wakeup` on D6 | **Polled only** — GPIO21 cannot wake ESP32-C3 from deep sleep |
| EEPROM storage | Text-based log entries | **Binary `ReadingRecord` struct** (compact, fixed-size, CRC-protected) |
| Battery voltage | `analogReadMilliVolts(A0) × 2` | Same — implemented with 16× averaging |
| Backend `models.py` | Planned separate file | **Not created** — schemas.py + database.py inline |

---

## iPhone Hotspot Notes

- Use a fixed hotspot name and password in iOS settings so credentials stay valid.
- Phone must stay awake with hotspot enabled until upload finishes (~15–60 s).
- The ESP32-C3 uses Wi-Fi STA mode to join the Personal Hotspot.
- iPhone relays traffic over cellular or its own Wi-Fi.
- If upload fails with Wi-Fi disconnect, move closer or disable Low Data Mode.

---

## Hardware Preparation Checklist

- [ ] Desolder DS3231 power LED (prevents 2–5 mA continuous drain)
- [ ] Replace TP4056 RPROG with 3 kΩ (400 mA charge current)
- [ ] Solder battery divider (200 kΩ + 200 kΩ) on BAT+/A0/GND
- [ ] Encase TEMT6000 in opaque housing/tape to block ambient light
- [ ] Mount button in accessible location on enclosure
- [ ] Verify voltages with multimeter before connecting battery
