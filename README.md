# Meter Buddy

Battery-powered ESP32-C3 firmware for counting electricity meter LED pulses and uploading stored readings on demand.

## Hardware Target

- Seeed Studio XIAO ESP32-C3
- DS3231 + AT24C32 I2C breakout
- TEMT6000 light sensor breakout powered continuously from 3.3V
- Upload button on D6 to GND
- LiPo battery with TP4056 charger
- 200 kOhm / 200 kOhm battery divider into A0

## Pin Map

| Function | XIAO pin | GPIO | Notes |
| --- | --- | --- | --- |
| Battery ADC | D0 / A0 | GPIO2 | 1:2 external divider |
| Unused | D1 | GPIO3 | Do not use for sensor power |
| Pulse wake | D2 | GPIO4 | Active-high deep-sleep GPIO wake |
| RTC wake | D3 | GPIO5 | DS3231 SQW/INT, active low |
| I2C SDA | D4 | GPIO6 | DS3231 + AT24C32 |
| I2C SCL | D5 | GPIO7 | DS3231 + AT24C32 |
| Upload button | D6 | GPIO21 | `INPUT_PULLUP`, active low |

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

## Upload Flow

1. Press the D6 upload button.
2. Firmware wakes from deep sleep.
3. It loads unsynced AT24C32 records.
4. It samples battery voltage.
5. It joins the configured iPhone Personal Hotspot.
6. It syncs system/RTC time from NTP while Wi-Fi is available.
7. It POSTs JSON to the configured HTTPS endpoint using Basic Auth.
8. Only HTTP `200` or `201` advances the sync cursor.
9. The radio shuts down and the ESP32-C3 returns to deep sleep.

## Current Firmware Notes

- Storage uses fixed-size EEPROM records instead of text logs to fit more readings into the 4 KB AT24C32.
- Pulse wake is implemented with the ESP32-C3 GPIO deep-sleep wake API because this target does not expose the classic ESP32 EXT1 wake API in the PlatformIO Arduino core used here.
- The TEMT6000 is expected to be always powered from 3.3V; otherwise it cannot wake the MCU on a pulse.
- If pulses arrive within `PulseAwakeThresholdMs`, firmware stays awake and counts interrupts until `PulseAwakeQuietMs` elapses, avoiding repeated deep-sleep churn during high load.
- Upload button sessions also perform NTP sync and adjust the DS3231 before returning to sleep.
- The diagnostics path stays awake on USB/power-on by default. Set `StayAwakeOnUsbBoot = false` for production.
- RTC time-setting and richer serial provisioning are not implemented yet; current config is compile-time via `local_config.h`.
