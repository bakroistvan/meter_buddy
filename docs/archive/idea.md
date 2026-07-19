# Hardware Summary: Battery-Powered Electricity Meter Pulse Logger
**Target Application:** Low-power data logger counting 1000 imp/kWh electricity meter flashing LEDs.
**Data Retrieval:** On **button press**, the ESP32 wakes, joins your **iPhone Personal Hotspot** as Wi-Fi STA, and **POST**s the accumulated log to your remote **HTTPS** endpoint using **HTTP Basic Authentication**.

---

## 📦 System Component Specifications

### 1. Core Processor & Radio Module
* **Component:** Seeed Studio XIAO ESP32-C3
* **Primary Role:** Handles pulse interrupts, coordinates I2C communication with the RTC/EEPROM, samples battery voltage on wake, performs on-demand HTTPS upload over Wi-Fi STA when the upload button is pressed, and manages deep-sleep states.
* **Key Spec:** ~43–44 μA deep-sleep current draw. Integrated battery pads on the underside.

### 2. Timekeeping & Non-Volatile Storage Module
* **Component:** DS3231 + AT24C32 I2C Breakout Board
* **Primary Role:** Maintains absolute system time and stores temporary hourly/daily pulse counts.
* **Key Spec (DS3231):** Temperature-compensated crystal oscillator with < 2 minutes of drift per year. Supports hardware alarm interrupts.
* **Key Spec (AT24C32):** 32 Kilobits (4 Kilobytes) of non-volatile EEPROM memory. Holds over 1,000 text-based log entries independently of the MCU.

### 3. Sensor Module
* **Component:** TEMT6000 Ambient Light Sensor Breakout
* **Primary Role:** Detects the physical flashes from the electricity meter’s pulse LED.
* **Key Spec:** High-sensitivity visible-light phototransistor. Acts as an instant hardware wakeup trigger for the microcontroller.

### 4. Power Supply Array
* **Component:** KXD 383450PL M Lithium-Polymer (LiPo) Battery
* **Primary Role:** Total system primary energy reservoir.
* **Key Spec:** 3.7V nominal voltage, 650 mAh total capacity (~2,340 Coulombs). Estimated system battery life: 1.5 to 2 years per charge.

### 5. Charging Module (Hardware Modified)
* **Component:** TP4056-1A-MU Linear Charger Module
* **Primary Role:** Recharges the 650 mAh LiPo battery safely via USB connection.
* **Mandatory Modification:** The standard 1.2 kΩ RPROG/R3 resistor must be desoldered and replaced with a **3 kΩ resistor** to lower the default output from 1000 mA down to **400 mA**.
* **Charge Performance:** Fully charges the 650 mAh battery in ~2 hours at the safe 400 mA current limitation.

### 6. Upload Trigger Button
* **Component:** Momentary push button (normally open)
* **Primary Role:** Manual trigger to start a data upload session. Wakes the ESP32 from deep sleep and initiates Wi-Fi join + HTTPS POST.
* **Key Spec:** Tactile switch with one leg to **D6** and one leg to **GND**. Firmware uses `INPUT_PULLUP` on D6 (active **LOW** on press). Debounce in software (~50 ms).

### 7. Battery Voltage Monitor (External Divider)
* **Component:** Two **200 kΩ** resistors (1% tolerance preferred; 220 kΩ also acceptable)
* **Primary Role:** Scales the 3.0–4.2 V LiPo voltage to a safe ADC range. The XIAO ESP32-C3 **does not** connect `BAT+` to an ADC internally—a divider is required.
* **Key Spec:** Resistor divider ratio **1:2** (equal R1 and R2). Continuous draw from the divider at 4.2 V is ~10 µA—negligible vs deep-sleep budget.

---

## 🔌 Hardware Interconnection Architecture

### Power Network Wiring
1. Connect the **KXD Battery (+) Positive lead** to both the **B+ pad** on the TP4056 module and the **BAT+ pad** on the underside of the XIAO ESP32-C3.
2. Connect the **KXD Battery (-) Negative lead** to both the **B- pad** on the TP4056 module and the **GND pad** on the underside of the XIAO ESP32-C3.
3. Route **3.3V out** from the XIAO ESP32-C3 pin header to the **VCC pin** of the DS3231 module.
4. Route **GND** from the XIAO ESP32-C3 pin header to the **GND pin** of the DS3231 module and the **GND pin** of the TEMT6000 module.
5. *Low-Power Trick:* Connect the **VCC pin** of the TEMT6000 module to a digital GPIO pin (e.g., **D1**) instead of continuous 3.3V power. Program the pin `HIGH` only during active calibration or monitoring windows to conserve power.
6. **Battery Voltage Divider:** Connect **R1 (200 kΩ)** from **BAT+** (same node as battery positive / TP4056 B+) to the junction node. Connect **R2 (200 kΩ)** from the junction node to **GND**. Connect the junction node to **A0 (D0 / GPIO2)** on the XIAO ESP32-C3. Use **ADC1** only—do **not** use D3 (ADC2) for battery reads while Wi-Fi is active.

```
BAT+ ─── R1 200kΩ ───┬─── A0 (D0)
                     │
                    R2 200kΩ
                     │
                    GND
```

### Data & Interrupt Signal Wiring
1. **I2C Bus:** Connect **D4 (SDA)** on the XIAO ESP32-C3 to **SDA** on the DS3231 board. Connect **D5 (SCL)** to **SCL** on the DS3231 board.
2. **Pulse Sensor Interrupt:** Connect the **Signal/OUT pin** of the TEMT6000 directly to **D2** on the XIAO ESP32-C3. Configure this pin in software as an external wakeup source (`ext0`) using a `RISING` edge signal.
3. **RTC Alarm Wakeup:** Connect the **SQW/INT pin** of the DS3231 module to **D3** on the XIAO ESP32-C3. The DS3231 wakes the processor **once every 24 hours** for daily EEPROM log writes only (upload is not scheduled).
4. **Upload Button:** Connect one leg of the momentary button to **D6** and the other leg to **GND**. No external pull-up resistor needed—enable `INPUT_PULLUP` in firmware.

---

## 🛠️ Required Hardware Preparation Checklist
* [ ] Desolder the 1.2 kΩ resistor at position RPROG on the TP4056 board. Solder a 3 kΩ surface-mount or axial resistor in its place.
* [ ] Desolder or slice the copper trace leading to the power-indicator LED on the DS3231 breakout board to prevent an unwanted 2–5 mA continuous drain.
* [ ] Disable or cut the charging circuit traces on the DS3231 module if utilizing a non-rechargeable CR2032 lithium backup coin cell.
* [ ] Encase the TEMT6000 sensor head inside an opaque black housing or wrap it tightly with black electrical tape when fixing it to the utility meter to eliminate outside ambient light interference.
* [ ] Mount the upload button where it is reachable when visiting the meter (e.g. on the enclosure lid). Verify D6 → GND wiring and that a press reads LOW in firmware.
* [ ] Solder the battery voltage divider (200 kΩ + 200 kΩ) from BAT+ to A0 (D0) and GND. Verify `analogReadMilliVolts(A0) × 2` reads ~3.7 V on a partially charged cell (compare with a multimeter).

---

## 📡 On-Demand Data Upload (HTTPS POST)

### User workflow
1. On your iPhone: **Settings → Personal Hotspot → Allow Others to Join** (note the hotspot name and password).
2. Stand near the meter logger (hotspot range is typically a few metres).
3. **Press and hold** the upload button for ~1 s (debounced in firmware).
4. Device wakes, joins the iPhone hotspot, POSTs stored readings to your server, then returns to deep sleep.
5. Optional: confirm success via serial debug LED blink pattern or server logs.

### Overview
The device stays offline until you explicitly request a sync. No calendar-based upload—only the button starts the Wi-Fi + HTTPS session.

```
Deep sleep ──► Button press (D6) ──► Wake ESP32
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              Read EEPROM         Sample battery      Build JSON body
              (hourly/daily         (A0 divider,       from stored counts
               pulse counts)         16× average)       + battery_v
                    │                   │
                    └─────────┬─────────┘
                              ▼
                        Wi-Fi STA join
                        (iPhone Personal Hotspot)
                              │
                              ▼
                              HTTPS POST + Basic Auth
                              (via iPhone cellular/Wi-Fi
                               internet to your server)
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
              2xx response                            failure: keep data,
              mark sync timestamp                       show error blink,
              in EEPROM                               allow retry on
                    │                                 next button press
                    ▼
              Wi-Fi disconnect → deep sleep
```

### HTTP request shape
| Item | Value |
|------|--------|
| Method | `POST` |
| URL | Configurable HTTPS endpoint (e.g. `https://example.com/api/meter-buddy/upload`) |
| Auth | `Authorization: Basic <base64(user:password)>` |
| Body | `Content-Type: application/json` (recommended) |

Example payload:

```json
{
  "device_id": "meter-buddy-001",
  "meter_impulses_per_kwh": 1000,
  "period_start": "2026-05-01T00:00:00Z",
  "period_end": "2026-06-16T14:30:00Z",
  "upload_trigger": "button",
  "battery_v": 3.87,
  "battery_pct_est": 62,
  "readings": [
    { "timestamp": "2026-05-01T12:00:00Z", "pulses": 42 },
    { "timestamp": "2026-05-01T13:00:00Z", "pulses": 38 }
  ]
}
```

Your server validates Basic Auth, stores or processes the JSON, and returns `200`/`201` on success. Non-success responses should leave data on the device for a later retry.

### Configuration (stored in EEPROM or NVS)
Provision once (USB serial or compile-time defaults for development):

| Setting | Purpose |
|---------|---------|
| iPhone hotspot SSID / password | Wi-Fi credentials for Personal Hotspot (update if you change hotspot name or password in iOS) |
| Upload URL | HTTPS POST endpoint |
| Basic Auth username / password | Server-side credential check |
| Device ID | Identifies this logger in multi-device setups |

Credentials must not be logged over serial in production builds.

**iPhone hotspot notes:**
* Use a **fixed hotspot name and password** in iOS settings so the ESP32 credentials stay valid.
* The phone must stay awake with hotspot enabled until the upload finishes (~15–60 s).
* iPhone relays traffic over cellular or its own Wi-Fi; the ESP32 only sees the hotspot as its upstream network.
* If upload fails with `WiFi disconnected`, move closer to the phone or disable Low Data Mode on the iPhone.

### TLS / HTTPS on ESP32-C3
* Use the ESP32 **WiFiClientSecure** (Arduino) or **esp_http_client** with TLS (ESP-IDF).
* Pin the server certificate or use the **certificate bundle** (`crt_bundle`) for Let's Encrypt and common CAs—required for reliable HTTPS without disabling verification.
* Keep the upload window short: connect → POST → disconnect radio → sleep.

### Power impact
Wi-Fi TX only runs during a **manual upload** (typically 15–60 s). This is even better for battery life than a scheduled monthly wake—you sync only when you visit the meter with your phone.

### Server-side expectations
* Accept `POST` with JSON body and Basic Auth.
* Respond with `200`/`201` and a small JSON ack (optional) so the firmware can mark the sync complete.
* Use HTTPS only; reject plain HTTP in production.
* Rate-limit and rotate Basic Auth credentials as you would for any IoT ingest endpoint.

---

## 🔋 Battery Voltage Monitoring

### What is measured
The ESP32 reports **pack voltage** via the external divider—not true mAh (no fuel gauge). Map voltage to an estimated percentage in firmware or on the server.

| Cell voltage (approx.) | Meaning |
|------------------------|---------|
| 4.15 – 4.20 V | Full |
| 3.70 V | ~50% (load-dependent) |
| 3.40 – 3.50 V | Low — plan a USB recharge visit |
| ≤ 3.30 V | Critical — recharge soon to avoid over-discharge |

### When to sample
| Event | Action |
|-------|--------|
| **Upload button press** | Read battery, include in HTTPS POST payload |
| **Daily RTC wake** | Optional: read and store last `battery_v` in EEPROM for trend logging |
| **Pulse wake (D2)** | Skip — keep wake time minimal |

Sample **before** or **after** Wi-Fi join (not during heavy TX). Average **16 reads** of `analogReadMilliVolts(A0)` and multiply by **2** to undo the divider.

### Firmware sketch (conceptual)

```cpp
uint32_t mv = 0;
for (int i = 0; i < 16; i++) {
  mv += analogReadMilliVolts(A0);
}
float battery_v = (mv / 16.0f) * 2.0f / 1000.0f;
```

Use `analogReadMilliVolts()` (factory-calibrated) rather than raw `analogRead()`.

### Pin note (D0 / A0)
D0 (GPIO2) is a strapping pin on ESP32-C3. Battery sense on A0 is Seeed’s recommended approach; if USB upload becomes unreliable, leave the divider connected but avoid pulling A0 low during boot, or move the divider tap to **D1 (GPIO3 / ADC1)** if D1 is free during the sample window.

### Limitations
* **Voltage ≠ exact SoC** — load and temperature shift the curve; treat `battery_pct_est` as approximate.
* **No charge-state reporting** — voltage rises when USB charges via TP4056; interpret readings on battery-only operation.
* **Not coulomb counting** — for exact mAh remaining you would need a fuel-gauge IC (e.g. MAX17048)—out of scope for this build.

---

## 💻 Software Stack (Firmware)

| Layer | Choice |
|-------|--------|
| Language | C++ |
| Build | PlatformIO |
| Framework | Arduino (ESP32 3.x on XIAO ESP32-C3) |
| HTTP | `HTTPClient` + `WiFiClientSecure` |
| Time / storage | RTClib (DS3231), I2C EEPROM helpers (AT24C32) |
| Upload trigger | GPIO **D6** button (`INPUT_PULLUP`, active LOW); optional `esp_sleep_enable_ext1_wakeup` on D6 so a press wakes from deep sleep |
| Battery sense | **A0 (D0)** via 200 kΩ / 200 kΩ divider; `analogReadMilliVolts(A0) × 2` on upload and optional daily wake |

**Removed from plan:** device-hosted Wi-Fi AP, BLE export, scheduled monthly upload, and home-router Wi-Fi. **iPhone Personal Hotspot** provides the upload path to the internet; your HTTPS server remains the data sink.
