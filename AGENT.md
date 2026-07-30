# Meter Buddy — Agent guide

Battery-powered ESP32-C3 device that counts utility-meter optical pulses, stores period readings, and uploads them over Wi‑Fi when the user short-presses the button. Long press toggles stay-awake / diagnostics.

## Single source of truth

| Doc | Role |
| --- | --- |
| [docs/intent_spec.md](docs/intent_spec.md) | User requirements only (no implementation choices) |
| [docs/firmware/fw_specification.md](docs/firmware/fw_specification.md) | Normative firmware behavior (stories, wake/IRQ, hardware assumptions) |

Index and archive map: [docs/README.md](docs/README.md).

## Other living docs

| Doc | Role |
| --- | --- |
| [docs/api/upload.md](docs/api/upload.md) | Firmware ↔ backend upload JSON contract |
| [README.md](README.md) | Build/flash, pin overview, hardware |
| [backend/README.md](backend/README.md) | FastAPI server, Docker, tests |

`docs/archive/` is **non-normative** history. Prefer SoT over archived notes.

## Repo map

| Path | Role |
| --- | --- |
| `include/`, `src/`, `platformio.ini` | Firmware (PlatformIO / Arduino) |
| `include/config.example.h` → `local_config.h` | Compile-time config (local file gitignored) |
| `tools/`, `meter_buddy.bat` | Build/flash/monitor helper |
| `backend/` | Upload API, SQLite, index UI |
| `docs/` | SoT + API contract |
| `.cursor/agents/explain-user-story.md` | Explains observed device behavior vs `main.cpp` |

## Firmware basics (see fw_specification for full truth)

- Deep sleep; GPIO **LOW** wake on button (D1), RTC (D3), pulse/TEMT6000 (D2).
- Awake pulse ISR: **FALLING**. Priority after GPIO wake: button > RTC > pulse default.
- Hot pulse counters in RTC RAM; LittleFS for committed periods; upload on short press.
- Status LED (D10): dim = awake, full = upload, patterns for RTC / stay-awake / errors.
- When changing behavior, update SoT in the same change (see `.cursor/rules/`).

## Backend basics

- FastAPI ingest at `POST /api/meter-buddy/upload` (Basic Auth).
- Contract: [docs/api/upload.md](docs/api/upload.md). Keep aligned with firmware upload payload.
