# Architecture

Meter Buddy is a monorepo with ESP32-C3 firmware and a small FastAPI backend.

## Packages

```text
meter_buddy/
├── include/, src/          # Firmware (PlatformIO / Arduino)
├── platformio.ini          # Firmware build config
├── tools/, meter_buddy.bat # Host-side firmware helper CLI
├── backend/                # FastAPI upload receiver + SQLite + index UI
└── docs/                   # Living documentation
```

### Firmware

- Target: Seeed Studio XIAO ESP32-C3
- Counts meter LED pulses, stores readings, uploads on button press
- Config: `include/config.example.h` + gitignored `include/local_config.h`
- Entry: `src/main.cpp`

### Backend

- Receives HTTPS (or local HTTP) JSON uploads with Basic Auth
- Stores dumps and readings in SQLite
- Serves a simple HTML index and dump JSON download/preview
- Live updates over WebSocket (`/ws`)
- Run locally with uvicorn or from `backend/` with Docker Compose

### Tools

- `meter_buddy.bat` → `tools/meter_buddy.py` wraps PlatformIO build/flash/monitor

## Data flow

1. Firmware accumulates pulse counts into period records (local storage).
2. User presses upload button → Wi-Fi → `POST /api/meter-buddy/upload`.
3. Backend validates, persists, returns `201` with `dump_id`.
4. Firmware advances sync cursor only on HTTP `200` or `201`.
5. Open browsers on `/` see new dumps; WebSocket clients get `new_dump` events.

## Shared contract

See [api/upload.md](api/upload.md).
