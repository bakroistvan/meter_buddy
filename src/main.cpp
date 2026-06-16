#include <Arduino.h>
#include <Wire.h>
#include <esp_sleep.h>
#include <WiFi.h>

#include "battery.h"
#include "config.h"
#include "pins.h"
#include "rtc_clock.h"
#include "storage.h"
#include "upload.h"

namespace {

RTC_DATA_ATTR uint32_t lastPulseWakeUnix = 0;

volatile uint32_t awakePulseCount = 0;
volatile uint32_t lastPulseRiseMs = 0;

void logLine(const char *message) {
  if (config::EnableSerialLogs) {
    Serial.println(message);
  }
}

void configurePins() {
  pinMode(pins::UploadButtonPin, INPUT_PULLUP);
  pinMode(static_cast<uint8_t>(pins::PulseWakePin), INPUT);
  pinMode(static_cast<uint8_t>(pins::RtcWakePin), INPUT_PULLUP);
}

void enterDeepSleep() {
  WiFi.mode(WIFI_OFF);

  esp_deep_sleep_enable_gpio_wakeup(
      (1ULL << pins::UploadButtonWakePin) | (1ULL << pins::RtcWakePin),
      ESP_GPIO_WAKEUP_GPIO_LOW);
  esp_deep_sleep_enable_gpio_wakeup(1ULL << pins::PulseWakePin, ESP_GPIO_WAKEUP_GPIO_HIGH);

  if (config::EnableSerialLogs) {
    Serial.flush();
  }
  esp_deep_sleep_start();
}

bool uploadButtonPressed() {
  if (digitalRead(pins::UploadButtonPin) != LOW) {
    return false;
  }
  delay(50);
  return digitalRead(pins::UploadButtonPin) == LOW;
}

void IRAM_ATTR onPulseRise() {
  const uint32_t now = millis();
  if (now - lastPulseRiseMs >= config::PulseDebounceMs) {
    ++awakePulseCount;
    lastPulseRiseMs = now;
  }
}

bool sleepMakesSenseAfterPulse(uint32_t timestamp) {
  if (timestamp == 0 || lastPulseWakeUnix == 0 || timestamp <= lastPulseWakeUnix) {
    return true;
  }

  const uint32_t intervalMs = (timestamp - lastPulseWakeUnix) * 1000UL;
  return intervalMs > config::PulseAwakeThresholdMs;
}

uint32_t countAwakeUntilQuiet() {
  awakePulseCount = 0;
  lastPulseRiseMs = millis();

  const uint32_t settleStart = millis();
  while (digitalRead(static_cast<uint8_t>(pins::PulseWakePin)) == HIGH &&
         millis() - settleStart < config::PulseDebounceMs * 4) {
    delay(1);
  }

  attachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(pins::PulseWakePin)), onPulseRise, RISING);

  const uint32_t started = millis();
  uint32_t lastCount = 0;
  uint32_t quietSince = millis();

  while (millis() - started < config::PulseAwakeMaxMs) {
    const uint32_t count = awakePulseCount;
    if (count != lastCount) {
      lastCount = count;
      quietSince = millis();
    }
    if (millis() - quietSince >= config::PulseAwakeQuietMs) {
      break;
    }
    delay(25);
  }

  detachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(pins::PulseWakePin)));
  return awakePulseCount;
}

void handlePulseWake(uint32_t timestamp) {
  logLine("pulse wake");
  const bool sleepNow = sleepMakesSenseAfterPulse(timestamp);
  lastPulseWakeUnix = timestamp;

  uint32_t pulses = 1;
  if (!sleepNow) {
    logLine("frequent pulses: counting while awake");
    pulses += countAwakeUntilQuiet();
  }

  storage::addPulses(timestamp, pulses);
}

void handleRtcWake(uint32_t timestamp) {
  logLine("rtc wake");
  rtc_clock::clearAlarm();
  const auto reading = battery::sample();
  storage::rollCurrentPeriod(timestamp, static_cast<uint16_t>(reading.volts * 1000.0f));
  rtc_clock::scheduleNextDailyAlarm();
}

void handleUploadWake() {
  logLine("upload wake");
  if (!uploadButtonPressed()) {
    logLine("upload button debounce rejected");
    return;
  }

  storage::UploadBatch batch{};
  if (!storage::loadUploadBatch(batch)) {
    logLine("failed to load upload batch");
    return;
  }

  const auto reading = battery::sample();
  const auto result = upload::sendBatch(batch, reading);
  if (config::EnableSerialLogs) {
    Serial.printf("upload result=%s records=%u\n", upload::resultName(result), batch.count);
  }

  if (result == upload::Result::Success) {
    storage::markSyncedThrough(batch.newestSequence);
  }
}

void handleDiagnosticsBoot() {
  logLine("diagnostics boot");
  storage::dump(Serial);
  const auto reading = battery::sample();
  Serial.printf("battery=%.2fV pct=%u\n", reading.volts, reading.percent);
}

} // namespace

void setup() {
  if (config::EnableSerialLogs) {
    Serial.begin(115200);
    delay(300);
  }

  configurePins();
  Wire.begin(pins::I2cSdaPin, pins::I2cSclPin);
  battery::begin();

  const bool rtcOk = rtc_clock::begin();
  const bool storageOk = storage::begin(Wire);
  if (!rtcOk) {
    logLine("rtc init failed");
  }
  if (!storageOk) {
    logLine("storage init failed");
  }

  const uint32_t timestamp = rtcOk ? rtc_clock::nowUnix() : 0;
  const esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();

  if (cause == ESP_SLEEP_WAKEUP_GPIO && digitalRead(static_cast<uint8_t>(pins::PulseWakePin)) == HIGH) {
    handlePulseWake(timestamp);
    enterDeepSleep();
  }

  if (cause == ESP_SLEEP_WAKEUP_GPIO && digitalRead(static_cast<uint8_t>(pins::RtcWakePin)) == LOW) {
    handleRtcWake(timestamp);
    enterDeepSleep();
  }

  if (cause == ESP_SLEEP_WAKEUP_GPIO && digitalRead(pins::UploadButtonPin) == LOW) {
    handleUploadWake();
    enterDeepSleep();
  }

  handleDiagnosticsBoot();
  rtc_clock::scheduleNextDailyAlarm();

  if (!config::StayAwakeOnUsbBoot) {
    enterDeepSleep();
  }
}

void loop() {
  delay(1000);
}
