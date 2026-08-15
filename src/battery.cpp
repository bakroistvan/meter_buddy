#include "battery.h"

#include <WiFi.h>
#include <esp_system.h>

#include "driver/adc.h"
#include "esp_adc_cal.h"

#include "config.h"
#include "pins.h"
#include "storage.h"

namespace battery {

namespace {

constexpr uint8_t kSampleCount = 16;
constexpr uint32_t kDefaultVrefMv = 1100;
constexpr float kDividerScale = 2.0f;

bool begun = false;
bool calOk = false;
esp_adc_cal_value_t calValueType = ESP_ADC_CAL_VAL_DEFAULT_VREF;
esp_adc_cal_characteristics_t calChars{};
adc1_channel_t adcChannel = ADC1_CHANNEL_0;

const char *valueTypeName(esp_adc_cal_value_t type) {
  switch (type) {
  case ESP_ADC_CAL_VAL_EFUSE_TP_FIT:
    return "efuse_tp_fit";
  case ESP_ADC_CAL_VAL_EFUSE_TP:
    return "efuse_tp";
  case ESP_ADC_CAL_VAL_EFUSE_VREF:
    return "efuse_vref";
  case ESP_ADC_CAL_VAL_DEFAULT_VREF:
    return "default_vref";
  default:
    return "unknown";
  }
}

bool efuseSupported(esp_adc_cal_value_t type) {
  return esp_adc_cal_check_efuse(type) == ESP_OK;
}

void logCalibration() {
  if (!config::EnableSerialLogs) {
    return;
  }
  Serial.printf(
      "battery adc cal source=%s ok=%d vref=%u atten=12dB channel=%d\n",
      valueTypeName(calValueType),
      calOk ? 1 : 0,
      static_cast<unsigned>(calChars.vref),
      static_cast<int>(adcChannel));
  if (!calOk) {
    Serial.println("battery adc WARNING: eFuse calibration unavailable; using default Vref");
  }
}

void ensureBegun() {
  if (!begun) {
    begin();
  }
}

uint32_t readCalibratedMilliVolts() {
  ensureBegun();

  uint32_t sum = 0;
  for (uint8_t i = 0; i < kSampleCount; ++i) {
    const int raw = adc1_get_raw(adcChannel);
    if (raw < 0) {
      continue;
    }
    sum += esp_adc_cal_raw_to_voltage(static_cast<uint32_t>(raw), &calChars);
    delay(5);
  }
  return sum / kSampleCount;
}

} // namespace

void begin() {
  const int8_t channel = digitalPinToAnalogChannel(pins::BatteryAdcPin);
  if (channel < 0 || channel >= SOC_ADC_MAX_CHANNEL_NUM) {
    if (config::EnableSerialLogs) {
      Serial.printf("battery adc ERROR: pin %u is not ADC1\n",
                    static_cast<unsigned>(pins::BatteryAdcPin));
    }
    begun = true;
    calOk = false;
    calValueType = ESP_ADC_CAL_VAL_DEFAULT_VREF;
    return;
  }

  adcChannel = static_cast<adc1_channel_t>(channel);
  analogReadResolution(12);
  analogSetPinAttenuation(pins::BatteryAdcPin, ADC_11db);
  pinMode(pins::BatteryAdcPin, ANALOG);
  adc1_config_channel_atten(adcChannel, ADC_ATTEN_DB_12);

  // Verify eFuse cal bits exist; characterize() picks the best scheme available.
  const bool hasEfuse =
      efuseSupported(ESP_ADC_CAL_VAL_EFUSE_TP_FIT) ||
      efuseSupported(ESP_ADC_CAL_VAL_EFUSE_TP) ||
      efuseSupported(ESP_ADC_CAL_VAL_EFUSE_VREF);
  if (!hasEfuse && config::EnableSerialLogs) {
    Serial.println("battery adc WARNING: no eFuse cal bits reported by esp_adc_cal_check_efuse");
  }

  calValueType = esp_adc_cal_characterize(
      ADC_UNIT_1,
      ADC_ATTEN_DB_12,
      ADC_WIDTH_BIT_12,
      kDefaultVrefMv,
      &calChars);

  calOk = (calValueType == ESP_ADC_CAL_VAL_EFUSE_TP_FIT ||
           calValueType == ESP_ADC_CAL_VAL_EFUSE_TP ||
           calValueType == ESP_ADC_CAL_VAL_EFUSE_VREF);
  begun = true;
  logCalibration();
}

bool calibrationOk() {
  ensureBegun();
  return calOk;
}

const char *calibrationSource() {
  ensureBegun();
  return valueTypeName(calValueType);
}

Reading sample() {
  const float volts = readCalibratedMilliVolts() * kDividerScale / 1000.0f;
  return {volts, estimatePercent(volts)};
}

Reading sampleForRecord() {
  ensureBegun();

  if (WiFi.getMode() != WIFI_OFF) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
  }

  delay(config::BatteryAdcSettleMs);
  return sample();
}

uint8_t estimatePercent(float volts) {
  // Piecewise-linear single-cell LiPo resting OCV → SoC.
  // Anchored so ~3.63 V (USB charge start 2026-08-02) maps near empty (~6%),
  // not the old linear 3.30–4.20 map which reported ~37% there.
  static constexpr struct {
    float volts;
    uint8_t percent;
  } kOcv[] = {
      {4.20f, 100}, {4.15f, 95}, {4.11f, 90}, {4.08f, 85}, {4.02f, 80},
      {3.98f, 75},  {3.95f, 70}, {3.91f, 65}, {3.87f, 60}, {3.85f, 55},
      {3.84f, 50},  {3.82f, 45}, {3.80f, 40}, {3.79f, 35}, {3.77f, 30},
      {3.75f, 25},  {3.73f, 20}, {3.71f, 15}, {3.69f, 10}, {3.61f, 5},
      {3.30f, 0},
  };
  constexpr size_t kCount = sizeof(kOcv) / sizeof(kOcv[0]);

  if (volts >= kOcv[0].volts) {
    return 100;
  }
  if (volts <= kOcv[kCount - 1].volts) {
    return 0;
  }

  for (size_t i = 0; i + 1 < kCount; ++i) {
    const float vHi = kOcv[i].volts;
    const float vLo = kOcv[i + 1].volts;
    if (volts <= vHi && volts >= vLo) {
      const float pHi = static_cast<float>(kOcv[i].percent);
      const float pLo = static_cast<float>(kOcv[i + 1].percent);
      const float t = (volts - vLo) / (vHi - vLo);
      const float pct = pLo + t * (pHi - pLo);
      return static_cast<uint8_t>(constrain(static_cast<int>(pct + 0.5f), 0, 100));
    }
  }
  return 0;
}

void noteResetReason() {
  if (esp_reset_reason() != ESP_RST_BROWNOUT) {
    return;
  }
  storage::setProtectionLocked(true);
  storage::markProtectionPendingBrownout();
  if (config::EnableSerialLogs) {
    Serial.println("protection: latched from ESP_RST_BROWNOUT");
  }
}

bool evaluateProtectionLock(float volts, bool usbPowered) {
  if (usbPowered) {
    if (storage::protectionLocked()) {
      storage::setProtectionLocked(false);
      if (config::EnableSerialLogs) {
        Serial.println("protection: cleared (USB powered)");
      }
    }
    return false;
  }

  if (storage::protectionLocked()) {
    if (volts >= config::BatteryRadioUnlockVolts) {
      storage::setProtectionLocked(false);
      if (config::EnableSerialLogs) {
        Serial.printf("protection: cleared V=%.3f >= unlock %.3f\n",
                      volts, config::BatteryRadioUnlockVolts);
      }
      return false;
    }
    return true;
  }

  if (volts < config::BatteryRadioBlockVolts) {
    storage::setProtectionLocked(true);
    storage::markProtectionPendingLowBattery();
    if (config::EnableSerialLogs) {
      Serial.printf("protection: latched low battery V=%.3f < block %.3f\n",
                    volts, config::BatteryRadioBlockVolts);
    }
    return true;
  }

  return false;
}

bool protectionLocked() {
  return storage::protectionLocked();
}

} // namespace battery
