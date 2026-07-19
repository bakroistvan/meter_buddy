# meter_buddy — Technical Specification & Implementation Plan

This document translates the high-level design goals from [intent.md](intent.md) into a concrete technical specification and implementation plan, incorporating the proposed unified storage architecture (LittleFS) and OTA update capabilities.

---

## 1. Hardware & Pinout Specification

The device targets the ESP32-C3 microcontroller (Seeed Studio XIAO ESP32C3) with 4 MB of internal flash.

**Pin Assignments (from include/pins.h):**
- **A0 (GPIO2)**: BatteryAdcWakePin / BatteryAdcPin — ADC input for battery voltage divider.
- **D2 (GPIO4)**: PulseWakePin — Light/pulse sensor input (active LOW). Must be deep-sleep wake capable.
- **D3 (GPIO5)**: RtcWakePin — DS3231 RTC interrupt/SQW output (active LOW). Triggers periodic 60-second wakeups.
- **D4 (GPIO6)**: I2cSdaPin — I2C SDA (for RTC).
- **D5 (GPIO7)**: I2cSclPin — I2C SCL (for RTC).
- **D1 (GPIO3)**: UploadButtonPin — User button (active LOW, internal pull-up).
- **D10 (GPIO10)**: AwakeLedPin — Debug/status LED.

*Note: The external AT24C32 EEPROM chip on the I2C bus will be deprecated and removed from the BOM in favor of internal flash storage.*

---

## 2. Storage Architecture

To address flash wear limits and ensure data resilience, storage is split into two tiers using the ESP32-C3's capabilities:

### Tier 1: Hot Accumulation (RTC RAM)
- **Mechanism:** Data is stored in RTC_DATA_ATTR variables, which persist through deep sleep but are lost on complete power failure.
- **State Stored:** Current window's pulse count (currentPulses), window start time (currentPeriodStart), and last pulse timestamp.
- **Lifecycle:** Mutated on every pulse wake (avoiding flash wear). Flushed to Tier 2 only when the 60-second RTC alarm fires.

### Tier 2: Committed Records (LittleFS)
- **Mechanism:** A single LittleFS partition on the ESP32 internal flash, replacing both the EEPROM ring buffer and NVS cold storage.
- **Partitioning:** ~1.5 MB LittleFS partition, leaving room for two 1.2 MB OTA app partitions.
- **File Structure:** 
  - An append-only log file (/records.bin) for reading records (timestamp, pulses, battery mV).
  - A sync pointer file (/sync.dat) tracking which records have been acknowledged by the server.
- **Lifecycle:** Written to once per minute (RTC wake). Truncated or compacted only after a successful upload. Wear-leveling is handled automatically by LittleFS.

---

## 3. Power & State Management

The device operates primarily in ESP32 deep sleep, waking only on specific GPIO triggers:

1. **Pulse Wake (GPIO4 LOW):**
   - Increment pulse count in RTC RAM.
   - If pulses are rapid, stay awake briefly to accumulate before sleeping.
2. **RTC Wake (GPIO5 LOW):**
   - Fires every 60 seconds.
   - Read battery voltage (A0).
   - Package current RTC RAM state into a record and append to LittleFS.
   - Reset RTC RAM counters and schedule next DS3231 alarm.
3. **Button Wake (GPIO3 LOW):**
   - Short press: Trigger Wi-Fi connection and upload batch.
   - Long press (4s): Enter diagnostic mode (stay awake, pulse LED, accept serial commands).

---

## 4. Upload & OTA Model

- **Upload Trigger:** Manual short button press.
- **Flow:**
  1. Wake up and roll the current period if any pulses exist.
  2. Connect to Wi-Fi.
  3. Sync time via NTP and update the DS3231 RTC.
  4. Read a batch of unacknowledged records from LittleFS.
  5. POST JSON payload to the backend via HTTPS.
  6. On HTTP 200/201, advance the sync pointer in LittleFS and delete acknowledged records.
- **OTA Updates (HTTPUpdate):**
  - Following a successful data upload, the device queries a /firmware/version endpoint.
  - If a newer version is available, it pulls the .bin via HTTPS.
  - The firmware is flashed to the inactive OTA slot (pp1), and the device reboots.

---

## 5. Implementation Plan

The transition to this architecture can be executed in three phases to ensure stability:

### Phase 1: Storage Migration (LittleFS)
1. **Partition Table:** Create partitions.csv configuring two OTA app slots (~1.2 MB each) and one LittleFS data slot (~1.5 MB). Update platformio.ini to use it.
2. **Remove EEPROM Logic:** Delete src/storage.cpp (EEPROM ring buffer) and src/cold_storage.cpp (NVS).
3. **Implement LittleFS Storage:** Create a new storage.cpp backed by LittleFS. Implement an append-only log for records and a robust sync pointer update mechanism.
4. **Hot Counters:** Ensure currentPulses and currentPeriodStart are strictly maintained in RTC_DATA_ATTR and only written to LittleFS on the 60s boundary.

### Phase 2: OTA Implementation
1. **HTTPUpdate Integration:** Update upload.cpp to include the HTTPUpdate.h workflow.
2. **Backend API Check:** Implement the sequence to check for a new version after a successful data upload.
3. **Rollback Safety:** Add esp_ota_mark_app_valid_cancel_rollback() in setup() to ensure bad OTA updates automatically revert on crash.

### Phase 3: Cleanup & Optimization
1. **Hardware Update:** Update documentation (and eventually hardware revisions) to reflect the removal of the I2C EEPROM.
2. **Diagnostics:** Update the serial REPL commands (dump, status, clear) to interface with the new LittleFS storage.
3. **Power Tuning:** Verify sleep currents with the new partition and flash layout to ensure no regressions.
