#pragma once

#include <Arduino.h>

namespace battery {

struct Reading {
  float volts;
  uint8_t percent;
};

void begin();

// True after begin() when characterization used eFuse (not default Vref).
bool calibrationOk();

// Short label for logs: "efuse_tp_fit", "efuse_tp", "efuse_vref", "default_vref", "none".
const char *calibrationSource();

// Immediate ADC sample (eFuse-calibrated mV × divider). Prefer sampleForRecord() for
// values stored on RTC rolls / uploads.
Reading sample();

// Force Wi-Fi off, wait BatteryAdcSettleMs, then sample(). Use for RTC roll and upload.
Reading sampleForRecord();

uint8_t estimatePercent(float volts);

// If last reset was brown-out, latch protection lock (LittleFS) even if V bounced.
void noteResetReason();

// Apply block/unlock hysteresis vs USB. Returns true when protection remains/latches.
bool evaluateProtectionLock(float volts, bool usbPowered);

// Thin wrapper over storage::protectionLocked().
bool protectionLocked();

} // namespace battery
