# Wiring Guide — Meter Buddy

Wiring follows the pin assignments defined in `include/pins.h`.

---

## Pin Assignment Table

| XIAO Pin | GPIO | Connects to | Notes |
|----------|------|-------------|-------|
| D2       | 4    | TEMT6000 OUT | Pulse signal, ext0 wake on RISING |
| D1       | 3    | Upload button → GND | Deep-sleep wake on LOW |
| D3       | 5    | DS3231 SQW/INT | Daily alarm wake, ext1 wake on LOW |
| D4       | 6    | DS3231 SDA   | I2C data line |
| D5       | 7    | DS3231 SCL   | I2C clock line |
| D0 / A0  | 2    | Battery divider midpoint | ADC, strapping pin — ensure floats HIGH at boot |
| 3.3V     | —    | DS3231 VCC, TEMT6000 VCC | |
| GND      | —    | Common ground | |

---

## Power Network

```
KXD LiPo 650mAh 3.7V
  ├─ (+) ─┬─ TP4056 B+
  │       └─ XIAO BAT+ pad (underside)
  │
  └─ (–) ─┬─ TP4056 B–
          └─ XIAO GND pad (underside)

XIAO 3.3V pin ─── DS3231 VCC, TEMT6000 VCC

All GNDs common: XIAO GND, DS3231 GND, TEMT6000 GND,
                  battery divider GND, button GND
```

---

## TEMT6000 Ambient Light Sensor

| TEMT6000 | XIAO pin |
|----------|----------|
| VCC      | 3.3V |
| GND      | GND |
| OUT/SIG  | D2 (GPIO4) |

> The TEMT6000 is powered from 3.3V (not a GPIO pin) so it can wake the ESP32-C3 from deep sleep via a pulse on D2. See `include/pins.h`.

---

## DS3231 RTC + AT24C32 EEPROM Module

| DS3231 board | XIAO pin | Notes |
|-------------|----------|-------|
| VCC         | 3.3V     | |
| GND         | GND      | |
| SDA         | D4 (GPIO6) | |
| SCL         | D5 (GPIO7) | |
| SQW/INT     | D3 (GPIO5) | Active LOW alarm output |

> Add 4.7 kΩ pull-up resistors from SDA and SCL to 3.3V if your breakout board does not have them built-in.

---

## Upload Button

| Button leg | XIAO pin |
|-----------|----------|
| One leg   | D1 (GPIO3) |
| Other leg | GND |

> No external pull-up resistor. Firmware enables `INPUT_PULLUP` on D1. A press reads LOW and wakes the ESP32 from deep sleep.

---

## Battery Voltage Divider

```
BAT+ ─── R1 200kΩ ───┬─── A0 / D0 (GPIO2)
                      │
                     R2 200kΩ
                      │
                     GND
```

- Divider ratio: **1:2** (multiply ADC reading by 2)
- Use 1% tolerance resistors (200 kΩ each; 220 kΩ also acceptable)
- **D0 is a strapping pin on ESP32-C3.** Do not pull it LOW during boot. The divider resistors are high enough (200k to BAT+, 200k to GND) that at boot the pin sits at ~1.85V (well above the LOW threshold).

---

## TP4056 Charger Modification

- Desolder the 1.2 kΩ RPROG resistor
- Replace with **3 kΩ** resistor (sets charge current to ~400 mA)
- Input: USB 5V
- Output: B+ / B– to battery and XIAO BAT+/GND pads

---

## Hardware Preparation Checklist

* [ ] Desolder DS3231 power LED (prevents 2–5 mA continuous drain)
* [ ] Replace TP4056 RPROG with 3 kΩ (400 mA charge current)
* [ ] Solder battery divider (200k + 200k) on BAT+/A0/GND
* [ ] Encase TEMT6000 in opaque housing/tape to block ambient light
* [ ] Mount button in accessible location on enclosure
* [ ] Verify voltages with multimeter before connecting battery

---

## Quick Reference: `idea.md` vs `pins.h`

| Function | idea.md pin | pins.h pin |
|----------|-------------|------------|
| TEMT6000 VCC | 3.3V | **3.3V** (always on) |
| Upload button | D1 (GPIO3) | D1 (GPIO3) — updated |
| TEMT6000 OUT | D2 (GPIO4) | D2 (GPIO4) — unchanged |
| DS3231 alarm | D3 (GPIO5) | D3 (GPIO5) — unchanged |
| I2C SDA/SCL | D4/D5 | D4/D5 — unchanged |
| Battery ADC | A0/D0 | A0/D0 — unchanged |
