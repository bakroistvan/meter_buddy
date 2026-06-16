#include "battery.h"

#include "pins.h"

namespace battery {

void begin() {
  analogReadResolution(12);
  analogSetPinAttenuation(pins::BatteryAdcPin, ADC_11db);
}

Reading sample() {
  uint32_t mv = 0;
  for (uint8_t i = 0; i < 16; ++i) {
    mv += analogReadMilliVolts(pins::BatteryAdcPin);
    delay(5);
  }

  const float volts = (mv / 16.0f) * 2.0f / 1000.0f;
  return {volts, estimatePercent(volts)};
}

uint8_t estimatePercent(float volts) {
  if (volts >= 4.20f) {
    return 100;
  }
  if (volts <= 3.30f) {
    return 0;
  }

  const float pct = (volts - 3.30f) * 100.0f / (4.20f - 3.30f);
  return static_cast<uint8_t>(constrain(static_cast<int>(pct + 0.5f), 0, 100));
}

} // namespace battery

