# Meter Buddy

Battery-powered ESP32-C3 firmware for counting electricity meter LED pulses and uploading stored readings on demand.

## Repository layout

| Path | Role |
| --- | --- |
| `include/`, `src/`, `platformio.ini` | Firmware (PlatformIO / Arduino) |
| `tools/`, `meter_buddy.bat` | Firmware build/flash helper CLI |
| `backend/` | FastAPI upload receiver, SQLite store, index UI |
| `docs/` | Living docs (intent, API contract, wiring, architecture) |

See [docs/README.md](docs/README.md) for the full documentation index and [docs/architecture.md](docs/architecture.md) for package boundaries.

## Hardware Target

- Seeed Studio XIAO ESP32-C3
- DS3231 + AT24C32 I2C breakout
- TEMT6000 light sensor breakout powered continuously from 3.3V
- Upload button on D1 to GND
- LiPo battery with TP4056 charger
- 200 kOhm / 200 kOhm battery divider into A0

## Pin Map

| Function | XIAO pin | GPIO | Notes |
| --- | --- | --- | --- |
| Battery ADC | D0 / A0 | GPIO2 | 1:2 external divider |
| Upload button | D1 | GPIO3 | `INPUT_PULLUP`, active low, deep-sleep wake |
| Pulse wake | D2 | GPIO4 | Active-high deep-sleep GPIO wake |
| RTC wake | D3 | GPIO5 | DS3231 SQW/INT, active low |
| I2C SDA | D4 | GPIO6 | DS3231 + AT24C32 |
| I2C SCL | D5 | GPIO7 | DS3231 + AT24C32 |
| Pulse LED | D9 | GPIO9 | Dedicated short flash for each accepted pulse |
| Status LED | D10 | GPIO10 | Debug/status blink patterns |

## Configuration

Defaults live in `include/config.example.h`. For real credentials, create `include/local_config.h` with the same `config` namespace values. `local_config.h` is ignored by git.

At minimum, configure:

- `DeviceId`
- `WifiSsid`
- `WifiPassword`
- `UploadUrl`
- `BasicAuthUser`
- `BasicAuthPassword`
- `TlsCaCert` or development-only `AllowInsecureTls`

## Build

Use the helper wrapper:

```powershell
.\meter_buddy.bat build
```

The wrapper creates `.venv`, installs PlatformIO if needed, and keeps PlatformIO's core cache in `.platformio-core`.

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install platformio
$env:PLATFORMIO_CORE_DIR='.\.platformio-core'
.\.venv\Scripts\python -m platformio run
```

## Flash and Monitor

```powershell
.\meter_buddy.bat flash
.\meter_buddy.bat flash --port COM5
.\meter_buddy.bat monitor --port COM5
.\meter_buddy.bat flash-monitor --port COM5
```

`upload` is also available as an alias for `flash`:

```powershell
.\meter_buddy.bat upload --port COM5
```

## CI firmware build and artifact upload

Every push or pull request that changes the firmware sources triggers a GitHub Actions workflow that builds the PlatformIO firmware and uploads the resulting binary artifacts from the run summary.

The workflow is defined in [.github/workflows/build-firmware.yml](.github/workflows/build-firmware.yml) and publishes:

- `firmware.bin`
- `firmware.elf`
- `partitions.bin`

To flash the downloaded artifact to the device locally:

1. Download the `firmware-bin` artifact from the GitHub Actions run.
2. Extract the archive and locate the `firmware.bin` file.
3. Connect the ESP32-C3 over USB.
4. Run the PlatformIO uploader or the helper script with the binary:

```powershell
.\.venv\Scripts\python -m platformio run --target upload
```

If you prefer to flash a specific binary manually, use the Espressif uploader with the board's serial port:

```powershell
esptool.py --chip esp32c3 --port COM5 --baud 460800 write_flash 0x0 firmware.bin
```

## Upload Flow

1. Press the D1 upload button.
2. Firmware wakes from deep sleep.
3. It loads unsynced AT24C32 records.
4. It samples battery voltage.
5. It joins the configured iPhone Personal Hotspot.
6. It syncs system/RTC time from NTP while Wi-Fi is available.
7. It POSTs JSON to the configured HTTPS endpoint using Basic Auth.
8. Only HTTP `200` or `201` advances the sync cursor.
9. The radio shuts down and the ESP32-C3 returns to deep sleep.

JSON field names and auth are defined in [docs/api/upload.md](docs/api/upload.md).

## Backend

From the `backend/` directory:

```powershell
cd backend
docker compose up --build -d
```

Or run with a local venv (see [backend/README.md](backend/README.md)).

- Index UI: `http://127.0.0.1:8000/`
- Upload endpoint: `POST /api/meter-buddy/upload`

## Hardware wiring

See [docs/firmware/wiring.md](docs/firmware/wiring.md).

## Current Firmware Notes

- Storage uses fixed-size EEPROM records instead of text logs to fit more readings into the 4 KB AT24C32.
- Pulse wake is implemented with the ESP32-C3 GPIO deep-sleep wake API because this target does not expose the classic ESP32 EXT1 wake API in the PlatformIO Arduino core used here.
- The TEMT6000 is expected to be always powered from 3.3V; otherwise it cannot wake the MCU on a pulse.
- If pulses arrive within `PulseAwakeThresholdMs`, firmware stays awake and counts interrupts until `PulseAwakeQuietMs` elapses, avoiding repeated deep-sleep churn during high load.
- Upload button sessions also perform NTP sync and adjust the DS3231 before returning to sleep.
- The diagnostics path stays awake on USB/power-on by default. Set `StayAwakeOnUsbBoot = false` for production.
- RTC time-setting and richer serial provisioning are not implemented yet; current config is compile-time via `local_config.h`.
