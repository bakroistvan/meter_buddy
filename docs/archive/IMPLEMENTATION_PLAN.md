# Meter Buddy Implementation Plan

## Goal

Build battery-powered firmware for a Seeed Studio XIAO ESP32-C3 that counts an electricity meter LED pulse output, stores accumulated readings while offline, and uploads unsynced readings to a remote HTTPS endpoint only when the physical upload button is pressed.

## Firmware Scope

1. Create a PlatformIO Arduino project for the XIAO ESP32-C3.
2. Define the hardware pin map in one place.
3. Implement wake handling for:
   - pulse wake from the TEMT6000 signal,
   - daily RTC alarm wake from the DS3231,
   - upload button wake,
   - USB/power-on diagnostics.
4. Store metering records in the AT24C32 EEPROM on the DS3231 breakout.
5. Sample battery voltage through the external 1:2 divider on A0.
6. Sync the DS3231 from NTP during manual upload sessions.
7. Upload unsynced records over Wi-Fi STA using HTTPS POST and Basic Auth.
8. Preserve unsynced data unless the server returns HTTP 200 or 201.
9. Dynamically stay awake during frequent pulse bursts instead of immediately deep sleeping.
10. Return to deep sleep after each production wake path.

## File Layout

```text
platformio.ini
include/
  battery.h
  config.example.h
  config.h
  pins.h
  rtc_clock.h
  storage.h
  upload.h
src/
  battery.cpp
  main.cpp
  rtc_clock.cpp
  storage.cpp
  upload.cpp
```

## Implementation Milestones

1. Project scaffold and dependency configuration.
2. Fixed pin definitions matching the hardware wiring.
3. Configuration template for device identity, hotspot credentials, upload URL, Basic Auth, and TLS certificate.
4. EEPROM-backed fixed-size reading records with a header, sequence counter, and sync cursor.
5. RTC helper for DS3231 initialization, timestamp reads, NTP adjustment, alarm clearing, and next daily alarm scheduling.
6. Battery helper using 16 averaged `analogReadMilliVolts(A0)` samples multiplied by two.
7. Upload helper that syncs RTC time, builds compact JSON from unsynced records, and posts with `WiFiClientSecure` + `HTTPClient`.
8. Main wake dispatcher that selects the shortest possible path for each wake reason.
9. Frequent-pulse awake counting mode driven by measured pulse interval.
10. Build verification with PlatformIO.

## Validation Checklist

- Build succeeds with PlatformIO.
- I2C scan confirms DS3231 and AT24C32 addresses.
- EEPROM header initializes once and survives resets.
- Pulse simulation increments records without upload.
- RTC alarm rolls the active bucket.
- Button wake joins the configured iPhone hotspot.
- Button wake syncs DS3231 time from NTP.
- Successful HTTPS response advances the sync cursor.
- Failed HTTPS response leaves data available for retry.
- Battery voltage is within multimeter tolerance after divider compensation.
- Dense pulse bursts are counted while awake and persisted as a batch.
