# Meter Buddy Firmware Specification

**Status:** normative for firmware behavior. Must match `src/main.cpp` and helpers.  
**Companion:** [../intent_spec.md](../intent_spec.md) — user requirements without implementation choices.  
**Hardware target:** Seeed XIAO ESP32-C3, battery-powered, deep-sleep dominant.

This document describes **what the firmware does today**, including architecture and concurrent-wake behavior.

---

## 1. User stories

### US-1 — Isolated meter pulse
**Given** the device is in deep sleep,  
**When** a short optical S0 pulse (~3–50 ms) asserts `PulseWakePin` LOW,  
**Then** the device wakes, flashes the pulse LED ~100 ms, increments the hot pulse counter by 1 via `storage::addPulses` (RTC RAM; does **not** require LittleFS / `storage::begin()` success), and calls `enterDeepSleep()` (deep sleep when enabled; see US-9 if disabled). No Wi‑Fi. No LittleFS period append on this path.

### US-2 — Frequent / burst pulses
**Given** another pulse wake occurs more than 0 s and within `PulseAwakeThresholdMs` (8 s) after the last *accepted* pulse wake timestamp,  
**When** that wake is handled,  
**Then** the device stays awake, attaches a pulse ISR, accumulates additional pulses until `PulseAwakeQuietMs` (30 s) of quiet, stores `1 + ISR count`, then deep-sleeps (if deep sleep is enabled).

**Same-second caveat:** Timestamps are unix seconds (`rtc_clock` or `millis()/1000`). If `timestamp <= lastAcceptedPulseWakeUnix` (including two wakes in the same second), `sleepMakesSenseAfterPulse` treats the wake as isolated: credit 1 and sleep — burst mode does **not** run. Rapid sub-second trains after an isolated wake therefore rely on later wakes being in a later second, or on an already-awake ISR path.

### US-3 — RTC period roll (housekeeping)
**Given** deep sleep (or an awake diagnostics session),  
**When** the DS3231 alarm asserts `RtcWakePin` LOW and the RTC path runs,  
**Then** firmware clears/reschedules the alarm, samples battery via `battery::sampleForRecord()` (forces Wi‑Fi off, waits `BatteryAdcSettleMs`, then ADC sample), and calls `rollCurrentPeriod` with that mV (requires LittleFS / `storage::begin()` success). If hot pulses &gt; 0 and roll succeeds, a completed period record is appended and hot counters reset; if hot == 0, there is no append (period start may advance). With `EnableSerialLogs`, RTC roll always logs `hot_pulses` — including explicit `(no append)` when hot == 0, `-> appended` on success with hot &gt; 0, or `append failed storage_ok=…` when roll fails — plus battery V/pct. Then blinks the status LED once. From a deep-sleep RTC wake, it then calls `enterDeepSleep()`. From diagnostics, the REPL continues without sleeping.

### US-4 — Short upload button press
**Given** sleep or an awake session,  
**When** the upload button is pressed and released before `UploadLongPressMs` (4 s),  
**Then** the status LED runs `startPulseBlink` (toggles dim awake ↔ full every 400 ms), `flushAwakePulses(true)` folds any ISR pulses still only in `awakePulseCount` into the open hot period, then one `battery::sampleForRecord()` supplies mV for `rollCurrentPeriod` (local `ReadingRecord.batteryMv` only — not on the wire) and the same reading for top-level upload `battery_v` / `battery_pct_est` on the **first** `sendBatch` POST of the session (≤48 readings); follow-up truncated batches omit those keys (`nullptr` to `buildBody`). `handleUploadWake` owns one radio session: `ensureWifiConnected` once, `syncRtcFromNetwork` once (best-effort), then one or more JSON POSTs reuse the connection (including an empty heartbeat when there are no readings); the sync cursor advances only for batches that contained readings and received HTTP 200/201; a post-upload `flushAwakePulses(true)` credits pulses that arrived during Wi‑Fi/upload into the **new** open period (not this POST); on success with readings an optional OTA check may run while Wi‑Fi is still up (US-10); then `disconnectWifiIfAllowed` (no-op when `KeepWifiConnectedWhenAwake`); on network/HTTP failure the status LED does `rapidErrorBlink` before that disconnect; then `setAwake` restores dim idle PWM and the device sleeps unless stay-awake is active.

### US-5 — Long press toggles stay-awake
**Given** the upload button is held ≥ 4 s (from deep-sleep wake or while already awake),  
**When** the press is classified as long,  
**Then** `handleStayAwakeToggle()` flips `/stay_awake.dat` (`StayAwakeBoot`); **no upload** runs. After release wait:
- **Newly enabled** → status LED does full (`setOn`) + `doubleBlink` + `setAwake`; session stays awake / enters `enterStayAwakeMode` (diagnostics).
- **Newly disabled** → status LED does `rapidErrorBlink`; then `enterDeepSleep()`.

Exit stay-awake is also via diagnostics serial command `x` (clears the flag and sleeps).

### US-6 — Stay-awake / diagnostics
**Given** the flash stay-awake flag is set **or** a USB CDC host is open (`Serial.isPlugged() && Serial.isConnected()`),  
**When** cold boot completes, a long-press **enable** path runs, or a short upload finishes while stay-awake applies,  
**Then** the device stays awake with dim PWM status LED, pulse ISR attached, and a serial REPL. On entry, `handleDiagnosticsBoot()` prints a LittleFS hex dump (`storage::hexdump`), samples battery, then prints the help line and loops. Commands (first-letter match unless noted):

| Command | Action |
| --- | --- |
| `d` / `dump…` | Print open-hot summary (`storage_ok`, `hot_pulses`, `hot_start`) and a note that JSON `readings` are rolled LittleFS only (open hot is not included until RTC roll or upload); then `loadUploadBatch` → print `upload::buildBody(batch, &reading)` with `battery::sample()` — same encoder as `sendBatch`, passing the sample so top-level battery keys are present (immediate `sample()`, does **not** force Wi‑Fi off / settle; no roll, no network). Readings in the preview are `timestamp` / `period_start` / `pulses` only |
| `h` / `hexdump…` | `storage::hexdump` — hex of `/records.bin`, `/sync.dat`, `/stay_awake.dat` |
| `c` / `clear…` | `storage::clear()` |
| `s` / `status…` | Battery via `sample()` plus `adc_cal=<source> ok=<0/1>` (`calibrationSource` / `calibrationOk`), Wi‑Fi, live `awakePulseCount`, GPIO levels, UTC time, next RTC alarm; plus `storage_ok` (`storage::available()`), `unsynced`, `hot_pulses` (`currentPulses()`), `hot_start` (`currentPeriodStart()`), `awake_count` (typing `sleep` is **not** sleep — `s` runs `status`) |
| `t` / `time` | Current UTC time (human format) |
| `u` / `upload…` | Force upload (`handleUploadButton(true)`) |
| `r` / `reboot…` | `ESP.restart()` |
| `x` | Clear stay-awake flag and `enterDeepSleep()` |

Command `x` clears the stay-awake flag and calls `enterDeepSleep()`. A long-press **disable** while in diagnostics also clears the flag (via toggle) and calls `enterDeepSleep()` after release wait.

**Scope note:** Pulse and RTC deep-sleep wake paths always call `enterDeepSleep()` and do **not** consult `shouldStayAwake()`. With `EnableDeepSleep=true` that means sleep; with deep sleep disabled those calls return and `setup` ends into Arduino `loop()` (no diagnostics REPL, no pulse ISR unless attached elsewhere). USB stay-awake is therefore only effective on cold boot, upload-finish, and long-press **enable** paths (plus stay-awake mode once entered).

Command `x` clears the stay-awake flag and calls `enterDeepSleep()` (no-op sleep when deep sleep is disabled; REPL continues).

If `KeepWifiConnectedWhenAwake` is true, entering stay-awake also connects Wi‑Fi and NTP-syncs the RTC before the REPL. Long-press entry uses `beginTimeOnly()` and does not itself schedule/clear the RTC alarm; a still-asserted RTC pin may fire `handleRtcWake` on the first diagnostics poll.

### US-7 — Production cold boot
**Given** power-on / reset with no GPIO wake cause, stay-awake not required, and `EnableDeepSleep=true`,  
**When** boot completes,  
**Then** the next RTC alarm is scheduled (if RTC is available) and the device enters deep sleep immediately (no REPL). If deep sleep is disabled, see US-9.

### US-8 — LED meanings
| LED | Pin | Meaning |
| --- | --- | --- |
| Pulse LED | D8 | HIGH ~100 ms per accepted pulse (wake flash or ISR); off via FreeRTOS one-shot timer reset from ISR (not main-loop polling) |
| Status (`AwakeLed`) | D10 | Dim PWM (~30%, duty 77) = idle awake; `startPulseBlink` (dim ↔ full every 400 ms, `esp_timer`) = upload in progress; full (`setOn`) + `doubleBlink` + `setAwake` = stay-awake **enabled** (long-press toggle on); `blink` = RTC wake; `rapidErrorBlink` (10×) = upload failure **or** stay-awake **disabled** (long-press toggle off); off + pulldown = sleep. `setAwake` / `setOn` / `setOff` / `setSleep` / `pulse` stop the upload blink timer. |

### US-9 — Deep sleep disabled
**Given** `EnableDeepSleep=false`,  
**When** the device would otherwise sleep,  
**Then** `enterDeepSleep()` returns without sleeping. If stay-awake mode was entered, the pulse ISR is attached and the diagnostics REPL runs. If the device only falls through to Arduino `loop()` without having attached the ISR, `loop()` still flushes (if any), polls button/RTC, and optionally keeps Wi‑Fi alive — but pulses are **not** counted via ISR until stay-awake (or another attach path) has run.

### US-10 — OTA check after successful data upload
**Given** an upload succeeded and at least one reading was marked synced,  
**When** post-upload housekeeping runs,  
**Then** `upload::checkFirmwareUpdate()` is invoked while the upload wake’s Wi‑Fi session is still up; `disconnectWifiIfAllowed` runs afterward (unless `KeepWifiConnectedWhenAwake`). The check no-ops only if Wi‑Fi is already disconnected (e.g. connect failed earlier, or the radio dropped and was not restored).

---

## 2. Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                        src/main.cpp                         │
│  boot · wake resolve · handlers · ISR · sleep · diagnostics │
└───────────┬─────────────┬─────────────┬─────────────┬───────┘
            │             │             │             │
     ┌──────▼──────┐ ┌────▼────┐ ┌──────▼──────┐ ┌───▼────┐
     │  storage    │ │ upload  │ │ rtc_clock   │ │battery │
     │ LittleFS +  │ │ WiFi /  │ │ DS3231      │ │ ADC    │
     │ RTC hot     │ │ HTTPS / │ │ Alarm1      │ │        │
     │ counters    │ │ NTP/OTA │ │             │ │        │
     └─────────────┘ └─────────┘ └─────────────┘ └────────┘
            ▲
     pins.h · config.h · awake_led.h (header-only PWM)
```

### Module responsibilities

| Module | Role |
| --- | --- |
| `main.cpp` | Wake dispatch, pulse ISR, button classify, sleep arming, diagnostics REPL |
| `storage` | Hot counters in `RTC_DATA_ATTR`; LittleFS `/records.bin`, `/sync.dat`, `/stay_awake.dat`; getters `available()`, `currentPulses()`, `currentPeriodStart()`; `hexdump()` prints file hex to a `Stream` |
| `upload` | Session helpers `ensureWifiConnected` / `syncRtcFromNetwork` / `disconnectWifiIfAllowed`; `buildBody`/`sendBatch` (POST-only — may reconnect Wi‑Fi if dropped; no NTP; no disconnect; optional `const battery::Reading*` for top-level battery — `battery_v` at 3 decimal places; readings without battery keys; `errors[]`); OTA version check |
| `rtc_clock` | DS3231 time + Alarm1 schedule / clear |
| `battery` | A0 divider ADC: eFuse-calibrated mV × 2; `sample()` immediate; `sampleForRecord()` forces Wi‑Fi off + settle before sample (RTC roll / upload) |
| `awake_led` | Status LED PWM and blink patterns |
| `pins.h` / `config.h` | Pin map and compile-time knobs |

### Storage model (two tiers)

1. **Hot (RTC RAM):** `rtcCurrentPeriodStart`, `rtcCurrentPulses` — survive deep sleep, lost on power cut. Pulse counts saturate at 65535. Pulse wakes / flushes update these via `storage::addPulses` **without** a LittleFS write and **without** requiring `storage::begin()` / LittleFS mount success (write-endurance + pulse integrity when flash init fails). Exposed read-only as `currentPulses()` / `currentPeriodStart()`; `available()` reflects LittleFS init only.
2. **Burst timestamps (RTC RAM):** `lastAcceptedPulseWakeUnix` drives the frequent-pulse decision. `lastPulseWakeUnix` is written on each pulse wake but currently unused for decisions.
3. **Cold (LittleFS):** append-only period records; sync cursor; stay-awake flag. `rollCurrentPeriod`, `loadUploadBatch`, sync/mark, stay-awake flag, and `hexdump`/`clear` require successful `storage::begin()`. After a successful sync of readings, `compactRecords()` rewrites `/records.bin` to drop acknowledged sequences (see §6).

### Config knobs (defaults from `config.example.h`)

| Knob | Default | Purpose |
| --- | --- | --- |
| `PulseAwakeThresholdMs` | 8000 | Interval that triggers awake burst counting |
| `PulseAwakeQuietMs` | 30000 | Quiet time before sleep after burst mode |
| `PulseDebounceMs` | 50 | Pulse debounce / button release settle |
| `AwakePulseFlushMs` | 5000 | Periodic flush of ISR counts while awake |
| `WifiReconnectIntervalMs` | 10000 | Reconnect poll when keeping Wi‑Fi awake |
| `UploadLongPressMs` | 4000 | Short vs long press threshold |
| `RtcWakeIntervalSeconds` | 60 | DS3231 alarm period |
| `BatteryAdcSettleMs` | 80 | Pause after forcing Wi‑Fi off before ADC used for RTC roll / upload |
| `EnableDeepSleep` | true | Production sleep vs always-awake |
| `KeepWifiConnectedWhenAwake` | false | Keep Wi‑Fi after POST / on stay-awake entry |
| `StayAwakeBoot` | false | Compile-time default for stay-awake cache before/without flash file |
| `EnableSerialLogs` | true | Serial logging |
| `UploadUrl` | `https://…/api/meter-buddy/upload` | Full HTTPS upload endpoint |
| `BasicAuthUser` / `BasicAuthPassword` | `meter-buddy` / `change-me` | Must match backend `METER_BUDDY_AUTH_*` |
| `TlsCaCert` | `IsrgRootCerts` | Vendored ISRG Root X1 + X2 PEM (`include/certs/isrg_roots.h`); trust Let’s Encrypt server certs without pinning the rotating leaf |
| `AllowInsecureTls` | false | When false and `TlsCaCert` non-empty, `WiFiClientSecure` verifies the server; production must leave this false |

Refresh vendored roots with `script/refresh_isrg_roots.py` if ISRG CAs change (leaf renewals do not require a firmware flash).

### Hardware assumptions

Firmware depends on the following pin map and power topology (Seeed XIAO ESP32-C3). Wake edges are **GPIO level LOW** in deep sleep and **FALLING** for the awake pulse ISR — not RISING/`ext0`.

| Function | Pin | Notes |
| --- | --- | --- |
| Battery ADC | A0 / D0 (GPIO2) | External 1:2 divider; ADC1 raw → `esp_adc_cal_raw_to_voltage` (atten `ADC_ATTEN_DB_12` / Arduino `ADC_11db`); FW × 2 |
| Upload button | D1 (GPIO3) | To GND; `INPUT_PULLUP` — no external pull-up required |
| Pulse (TEMT6000 OUT) | D2 (GPIO4) | Active LOW into pull-up; deep-sleep wake capable |
| RTC alarm (DS3231 SQW) | D3 (GPIO5) | Active LOW |
| I2C SDA | D4 (GPIO6) | DS3231 |
| I2C SCL | D5 (GPIO7) | DS3231 |
| Pulse LED | D8 | Drive via series resistor on anode |
| Status LED | D10 | Drive via series resistor on anode |

**Meter constant (reference installation):**

Firmware config default is `MeterImpulsesPerKwh = 1000` (1000 pulses / kWh). Let:

| Symbol | Meaning |
| --- | --- |
| \(C\) | Meter constant (pulses / kWh); reference \(C = 1000\) |
| \(P_{\mathrm{W}}\) | Steady load power (W) |
| \(P_{\mathrm{kW}}\) | Steady load power (kW) = \(P_{\mathrm{W}} / 1000\) |
| \(T_{\mathrm{s}}\) | Time between consecutive pulses (s) |
| \(N_5\) | Pulse count over a 5-minute window at constant load |

Energy per pulse: \(1/C\) kWh. At constant power, pulse period and rate follow from \(E = P \cdot t\).

**Load ↔ time between pulses**

\[
T_{\mathrm{s}} = \frac{3\,600\,000}{C \cdot P_{\mathrm{W}}} = \frac{3600}{C \cdot P_{\mathrm{kW}}}
\]

\[
P_{\mathrm{W}} = \frac{3\,600\,000}{C \cdot T_{\mathrm{s}}}
\qquad
P_{\mathrm{kW}} = \frac{3600}{C \cdot T_{\mathrm{s}}}
\]

Pulse frequency (Hz): \(f = 1 / T_{\mathrm{s}} = C \cdot P_{\mathrm{kW}} / 3600\).

With **\(C = 1000\)**:

\[
T_{\mathrm{s}} = \frac{3600}{P_{\mathrm{W}}}
\qquad
P_{\mathrm{W}} = \frac{3600}{T_{\mathrm{s}}}
\]

Example: \(1\,\mathrm{kW}\) → \(T_{\mathrm{s}} = 3.6\,\mathrm{s}\) (one pulse every 3.6 s).

**Load ↔ pulses in 5 minutes**

Five minutes = \(5/60 = 1/12\) hour, so energy = \(P_{\mathrm{kW}}/12\) kWh:

\[
N_5 = \frac{C \cdot P_{\mathrm{kW}}}{12} = \frac{C \cdot P_{\mathrm{W}}}{12\,000}
\]

\[
P_{\mathrm{kW}} = \frac{12 \cdot N_5}{C}
\qquad
P_{\mathrm{W}} = \frac{12\,000 \cdot N_5}{C}
\]

With **\(C = 1000\)**:

\[
N_5 = \frac{P_{\mathrm{W}}}{12}
\qquad
P_{\mathrm{W}} = 12 \cdot N_5
\]

Example: \(1.2\,\mathrm{kW}\) → \(N_5 = 100\) pulses in 5 minutes; 50 pulses in 5 minutes → \(600\,\mathrm{W}\).

**Power / sensors (firmware prerequisites):**

- XIAO **3.3V** powers **DS3231** and **TEMT6000**; all module GNDs common with XIAO GND.
- **TEMT6000 must be always-on 3.3V** (not GPIO-switched); otherwise it cannot assert D2 during deep sleep.
- Battery path: **LiPo soldered to XIAO BAT+/GND**; USB charge via onboard **ETA4054** (~370 mA). Typical divider: **200 kΩ + 200 kΩ** (1%, 220 kΩ acceptable) from BAT+ to A0 midpoint to GND (matches FW 1:2 scale). No external TP4056 (or other charger) in parallel on the same cell.
- **A0/GPIO2 is a strapping pin** — must not be held LOW at boot; the high-impedance divider keeps the pin near mid-rail (~1.85 V on a typical cell).
- DS3231 breakouts often include **AT24C32 EEPROM**; firmware **does not use it** (LittleFS on internal flash only).
- Optional **4.7 kΩ** I2C pull-ups if the breakout lacks them.
- Build prep: desolder DS3231 module power LED (idle drain); opaque shield/tape on TEMT6000 against ambient light; keep upload button accessible; verify divider with a multimeter before connecting the battery.

**Battery ADC (firmware):**

- `battery::begin()` configures ADC1 on `BatteryAdcPin` at 12-bit width and `ADC_ATTEN_DB_12` (Arduino pin attenuation still set via `ADC_11db` alias), then calls `esp_adc_cal_characterize` (prefer eFuse TP_FIT → TP → VREF; else default Vref 1100 mV). `calibrationOk()` is true only for eFuse sources; serial logs `source=` / `ok=` and warns on default Vref.
- `sample()` averages 16× (`adc1_get_raw` → `esp_adc_cal_raw_to_voltage`), then × **2** divider → volts; `estimatePercent` maps volts → SoC via a **piecewise-linear single-cell LiPo resting OCV** table (descending breakpoints from 4.20 V → 100% through mid-curve knees such as 3.61 V → 5%, down to 3.30 V → 0%; clamp above/below ends; linear interpolate between neighbors, round to nearest int). Anchored for ETA4054 + LiPo so ~3.63 V (USB charge-start cal 2026-08-02) reports ~6%, not the old linear ~37%. Same curve is mirrored in the backend HTML UI fallback (`estimatePercentFromVolts`) when a reading lacks `battery_pct_est`.
- `sampleForRecord()` forces `WIFI_OFF` if needed, waits `BatteryAdcSettleMs` (default 80 ms), then `sample()`. Used by RTC roll (local `batteryMv` only) and once on upload wake (same sample for roll mV and first-POST top-level JSON). Diagnostics `status` / `dump` use `sample()` only.
- With `EnableSerialLogs`, battery voltage is logged at **3 decimal places** (`%.3fV`) on RTC roll, upload batch, `status`, and related paths.

---

## 3. Wake and interrupt sources

There is **no** ESP32 timer deep-sleep wake. Periodicity comes from the external DS3231 Alarm1 → `RtcWakePin` LOW.

Deep sleep arms **GPIO level wake (LOW)** on three pins (ESP32-C3 wake-capable GPIOs 0–5):

| Source | Pin | Sleep arm | Identification after wake | Handler |
| --- | --- | --- | --- | --- |
| Upload button | D1 / GPIO3 | `GPIO_LOW` | Pin still LOW (priority 1) | Short → upload; long → stay-awake toggle (enable → stay awake; disable → sleep) |
| RTC alarm | D3 / GPIO5 | `GPIO_LOW` | Pin still LOW if button not LOW | `handleRtcWake` |
| S0 pulse | D2 / GPIO4 | `GPIO_LOW` | Often already HIGH; **default** if GPIO wake | `handlePulseWake` (always credit 1) |
| Cold / other | — | — | Cause ≠ `ESP_SLEEP_WAKEUP_GPIO` | Stay or sleep via `shouldStayAwake()` |

### Resolve policy

```text
if cause != GPIO wake → None
else if UploadButton == LOW → UploadButton
else if RtcWake == LOW → Rtc
else → Pulse   // S0 edges are short; pin often already HIGH
```

### Awake-only inputs (not deep-sleep wake)

| Input | Mechanism | Notes |
| --- | --- | --- |
| Pulse | `attachInterrupt(..., FALLING)` | Only while awake / burst / upload / diagnostics |
| Button | Polled edge in diagnostics / `pollAwakeControls` | Not a GPIO ISR |
| RTC pin | Polled edge while awake | Alarm cleared inside `handleRtcWake` |

### Pre-sleep settling (`enterDeepSleep`)

1. Pulse / status LEDs off; Wi‑Fi off.
2. Wait until pulse pin is HIGH (up to `PulseDebounceMs * 4`) so level wake does not double-count.
3. Wait for upload button release with debounce (avoids re-wake loops).
4. Arm all three GPIO LOW wakes; `esp_deep_sleep_start()`.

---

## 4. Flow diagrams

### 4.1 Boot / wake dispatch

```mermaid
flowchart TD
  A[setup: OTA mark valid] --> B[initWakePinsAndLed]
  B --> C[resolveWakeSource]
  C -->|Pulse| P[initSubsystems timeOnly]
  P --> P2[handlePulseWake]
  P2 --> S[enterDeepSleep]
  C -->|Rtc| R[initSubsystems full RTC]
  R --> R2[handleRtcWake]
  R2 --> S
  C -->|UploadButton| U[classifyUploadPressFromWake]
  U -->|Long| L[storage begin + handleStayAwakeToggle]
  L -->|enabled| SA[enterStayAwakeMode]
  L -->|disabled| S
  U -->|Short| UP[handleUploadWake]
  UP -->|shouldStayAwake| SA
  UP -->|else| S
  C -->|None / cold| COLD[init serial + subsystems]
  COLD --> ALARM[scheduleNextWakeAlarm if RTC ok]
  ALARM -->|shouldStayAwake| SA
  ALARM -->|else| S
```

### 4.2 Pulse wake (isolated vs burst)

```mermaid
flowchart TD
  PW[handlePulseWake] --> LED[Pulse LED 100 ms]
  LED --> DEC{interval since last accepted pulse > Threshold?}
  DEC -->|yes / first| ONE[pulses = 1]
  DEC -->|no - frequent| BURST[countAwakeUntilQuiet via FALLING ISR]
  BURST --> SUM[pulses = 1 + ISR count]
  ONE --> STORE[storage::addPulses]
  SUM --> STORE
  STORE --> SLEEP[enterDeepSleep]
```

### 4.3 Concurrent sources while a handler is running

```mermaid
flowchart TD
  subgraph sleep["Deep sleep"]
    W[Any GPIO LOW] --> ONEWAKE[Single ESP_SLEEP_WAKEUP_GPIO]
    ONEWAKE --> PRIO[Sample pins: Button > RTC > Pulse default]
  end

  subgraph handlers["Active handler"]
    HP[Pulse isolated] -->|no ISR| MISS1[Other sources ignored until next sleep]
    HB[Burst countAwakeUntilQuiet] -->|pulse ISR only| MISS2[Button + RTC ignored]
    HR[handleRtcWake] -->|blocking| MISS3[Pulses / button ignored]
    HU[handleUploadWake] -->|pulse ISR attached| BUF[Pre-roll flush into batch; mid-upload flush into new period]
    HU --> MISS4[Button / RTC not polled]
    HD[Diagnostics / stay-awake] -->|ISR + poll| OK[Button / RTC edges handled]
  end
```

---

## 5. Multiple interrupts during an active handler

Deep-sleep wakes are **single-shot**, not nested. Concurrent GPIO assertions collapse into one wake cause plus **priority sampling** at boot. There is no deferred work queue beyond pulse ISR counters / pulse LED off timer / poll edge latches.

### 5.1 Matrix

| Active path | Pulse arrives | Button arrives | RTC asserts | Behavior |
| --- | --- | --- | --- | --- |
| Isolated `handlePulseWake` | Credited as the wake (+1); no ISR | Ignored | Ignored | Immediate sleep after store |
| `countAwakeUntilQuiet` | Counted by FALLING ISR (debounced) | **Ignored** (blocking loop) | **Ignored** | Pulse LED on/off via ISR + off timer; main path only waits for quiet |
| `handleRtcWake` | No ISR — may miss | Ignored | Cleared via RTC begin | Then sleep |
| `handleUploadWake` | ISR attached; `flushAwakePulses(true)` before roll and again after upload | Not re-polled | Not polled | Pre-roll flush includes pending `awakePulseCount` in this upload batch; mid-upload pulses land in the **new** open period (post-upload flush), not this POST |
| Classify long/short from wake | No ISR yet | Occupied | Ignored | Early path before full init |
| Diagnostics / stay-awake | ISR on | Edge → upload or toggle stay-awake (disable → sleep) | Edge → `handleRtcWake` | Serial REPL concurrent |
| `EnableDeepSleep=false` `loop()` | Via ISR if attached | `pollAwakeControls` | Same | Stay-awake attaches ISR |

### 5.2 Priority / misattribution rules (normative)

1. **GPIO wake + button still LOW** always wins over RTC and pulse, even if RTC also fired. The RTC alarm may remain asserted until a later RTC-handled path clears it.
2. **Default-to-Pulse:** a GPIO wake with button and RTC both HIGH is treated as a pulse (S0 edge usually gone). Spurious wakes with all pins HIGH are therefore counted as pulses.
3. **During burst counting or upload**, an RTC alarm may assert but is not handled until the next sleep/wake or a stay-awake poll — the period may run long; pulses still accumulate in the hot counter when an ISR is attached.
4. **Pulse during button/RTC wake** is not credited by `resolveWakeSource` and is missed unless an awake ISR is already attached on that path (upload attaches one; isolated RTC/pulse paths do not until burst mode).
5. **Burst decision** uses only `lastAcceptedPulseWakeUnix`. If the new timestamp is `<=` that value (same second or clock went backwards), the wake is treated as isolated — no burst counting.

### 5.3 Pulse ISR details (awake only)

- Edge: **FALLING** with `PulseDebounceMs` in the ISR.
- Shared `awakePulseCount` is read under `noInterrupts()` in flush/log paths.
- Pulse LED on is set in the ISR; LED off is a FreeRTOS one-shot timer (100 ms) reset via `xTimerResetFromISR`, so the flash still ends during blocking upload/Wi‑Fi work (status LED blink already used an independent `esp_timer`).

### 5.4 Re-wake mitigations

- Held button → `waitForUploadButtonRelease` before arming sleep.
- Pulse still LOW → settle wait before arming wakeup.
- Upload bounce → 50 ms debounce + stable HIGH window.
- Burst detection uses RTC unix timestamps in RTC memory across sleeps.

---

## 6. Upload behavior (detail)

1. Attach pulse ISR; status LED `startPulseBlink` (400 ms dim ↔ full). Forced upload from wake classify skips the extra 50 ms `uploadButtonPressed` debounce (already classified). Pulse LED flashes (~100 ms) via ISR + off timer for pulses during upload (§5.3); status blink is independent (`esp_timer`).
2. `flushAwakePulses(true)` so any pulses still only in `awakePulseCount` are written into the open hot period before it rolls.
3. One `battery::sampleForRecord()`; `rollCurrentPeriod` with that mV (closes the period into LittleFS; `batteryMv` is local storage only, not emitted on readings JSON). With `EnableSerialLogs`, the upload path may also call `storage::hexdump` before/after `rollCurrentPeriod` for serial debug (not the REPL `h` command).
4. `upload::ensureWifiConnected()` once. On failure, mark the wake failed and skip POSTs/NTP. On success, `upload::syncRtcFromNetwork()` once (best-effort — failure does not abort the wake).
5. Loop: `loadUploadBatch` → `upload::sendBatch(batch, includeBattery ? &reading : nullptr)` (`buildBody` + HTTPS/HTTP POST only; may call `ensureWifiConnected` again if the link dropped; no NTP; no disconnect). `includeBattery` starts true so the first POST of the session gets top-level `battery_v` / `battery_pct_est`; then set false so follow-up truncated batches omit those keys. On Success with `count > 0` → `markSyncedThrough`; continue while `truncated`; stop on empty/non-truncated or failure.
6. `flushAwakePulses(true)` again so pulses counted during Wi‑Fi/upload enter the **new** open period (not the batch just posted); detach ISR if this path attached it.
7. Success + had readings → optional OTA check via `upload::checkFirmwareUpdate()` while Wi‑Fi is still up; failure → `rapidErrorBlink`. Then `upload::disconnectWifiIfAllowed()` (skipped when `KeepWifiConnectedWhenAwake`); restore dim awake LED. USB flashing remains a valid primary install path.

### Sync cursor and compaction

When `markSyncedThrough(newestSequence)` runs after HTTP 200/201 with readings:

1. Persist the advanced sync cursor in `/sync.dat`.
2. Call `compactRecords()`, which rewrites `/records.bin` keeping only records with `sequence > syncedThrough` (temp file → remove → rename).

Empty successful heartbeats (`batch.count == 0`) do **not** call `markSyncedThrough` and therefore do **not** compact. `repairSyncState()` on boot mismatch may also invoke `compactRecords()`.

### TLS and server trust

Upload POSTs use `WiFiClientSecure` with HTTP Basic Auth (`BasicAuthUser` / `BasicAuthPassword`). Unless `AllowInsecureTls` is true, a non-empty `TlsCaCert` is passed to `setCACert` (default `IsrgRootCerts` — ISRG Root X1 + X2). Pin the public CA roots, not the server’s short-lived Let’s Encrypt leaf, so Caddy/automatic renewals on the backend do not require reflashing devices.

### Batch / error payload

The device always attempts a POST (empty `readings` allowed). Storage may attach `errors[]` such as `no_data`, `crc_mismatch`, `storage_unavailable`, `batch_truncated`. Sync advances only on HTTP 200/201 for batches that contained readings. An empty successful heartbeat does **not** error-blink. Payload includes `"upload_trigger":"button"`. Each reading object on the wire is `timestamp` / `period_start` / `pulses` only (no per-reading battery). Top-level battery keys appear only when `sendBatch` receives a non-null `battery::Reading*` (first batch of an upload wake, or diagnostics `dump` preview); `battery_v` is serialized with three decimal places (`String(volts, 3)` in `upload::buildBody`).

---

## 7. Stay-awake gates

```text
shouldStayAwake =
  (serialStarted AND Serial plugged AND CDC connected)
  OR storage::stayAwakeBoot()
```

`storage::stayAwakeBoot()` reflects the LittleFS flag (seeded from compile-time `StayAwakeBoot` before/without a flash file). Long-press **toggles** the flash flag via `handleStayAwakeToggle()` (in-RAM still updates even if LittleFS write fails): enable → LED full + `doubleBlink` + `setAwake`, session stays / enters stay-awake; disable → `rapidErrorBlink`, then `enterDeepSleep()` after button release wait. Clearing the flag is also via diagnostics command `x`, which then calls `enterDeepSleep()`.

---

## 8. Boot order (by design)

1. `esp_ota_mark_app_valid_cancel_rollback()` on every boot.
2. Pins + LED `setAwake()` first (user feedback + correct pin sample).
3. Resolve wake **before** Serial delay / heavy init.
4. Upload classify **before** LittleFS/I2C on the button wake path.
5. Pulse path is leanest: `initSubsystems(timeOnly)` only.

Timestamps use DS3231 when RTC init succeeded; otherwise `millis()/1000` fallback (affects burst intervals and period rolls).

Stay-awake enters `handleDiagnosticsBoot()` which never returns; Arduino `loop()` is unused in that mode. With deep sleep enabled and no stay-awake, `setup` sleeps and does not return.

**RTC while diagnostics:** `handleRtcWake` from the REPL rolls the period and reschedules the alarm but does **not** sleep — the REPL continues.

---

## 9. Consistency with code

This specification (with [intent_spec.md](../intent_spec.md)) is the firmware behavior contract. When changing `src/main.cpp` or helpers, update this file in the same change. Older notes archived under `docs/archive/` (`wiring.md`, `timing.md`, `input_flows.md`, etc.) are non-normative; drift is resolved in favor of **this document and the C++ sources**.
