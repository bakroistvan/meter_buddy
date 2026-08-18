#include "battery.h"

#include <WiFi.h>

#include "driver/adc.h"
#include "esp_adc_cal.h"

#include "config.h"
#include "pins.h"

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
  // Piecewise-linear ADC-volt → SoC for this pack + 1:2 divider (not textbook
  // 4.20 V OCV). Anchors from readings[].battery_v:
  //   100% ≈ 4.05 V rest after onboard ETA4054 CV (dumps 1171–1366)
  //   0%   ≈ 3.26 V last useful hour before empty cliff (dumps 989–1171)
  // Mid-curve from that discharge at ~11 mA (543 mAh to empty). Loaded charge
  // peaks (~4.12–4.18 V) clamp at 100%. ~3.63 V is ~25%, not the old 6%.
  static constexpr struct {
    float volts;
    uint8_t percent;
  } kOcv[] = {
      {4.05f, 100}, {3.994f, 95}, {3.938f, 90}, {3.908f, 85}, {3.890f, 80},
      {3.872f, 75}, {3.853f, 70},  {3.834f, 65}, {3.811f, 60}, {3.794f, 55},
      {3.775f, 50}, {3.758f, 45},  {3.737f, 40}, {3.714f, 35}, {3.690f, 30},
      {3.634f, 25}, {3.593f, 20},  {3.582f, 15}, {3.549f, 10}, {3.482f, 5},
      {3.26f, 0},
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

} // namespace battery
