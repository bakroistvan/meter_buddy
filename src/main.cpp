#include <Arduino.h>
#include <Wire.h>
#include <esp_sleep.h>
#include <esp_ota_ops.h>
#include <WiFi.h>

#include "battery.h"
#include "config.h"
#include "pins.h"
#include "rtc_clock.h"
#include "storage.h"
#include "upload.h"

namespace {

enum class WakeSource {
  None,
  Pulse,
  Rtc,
  UploadButton,
};

RTC_DATA_ATTR uint32_t lastPulseWakeUnix = 0;
RTC_DATA_ATTR uint32_t lastAcceptedPulseWakeUnix = 0;

volatile uint32_t awakePulseCount = 0;
volatile uint32_t lastPulseRiseMs = 0;
uint32_t lastAwakePulseFlushMs = 0;
uint32_t lastWifiCheckMs = 0;
bool awakePulseInterruptAttached = false;
bool rtcClockAvailable = false;
bool storageAvailable = false;

void logLine(const char *message) {
  if (config::EnableSerialLogs) {
    Serial.println(message);
  }
}

uint32_t currentTimestamp();

void logEvent(const char *event) {
  if (config::EnableSerialLogs) {
    Serial.printf("[%lu] %s\n", static_cast<unsigned long>(millis()), event);
  }
}

const char *wakeSourceName(WakeSource source) {
  switch (source) {
    case WakeSource::Pulse:
      return "pulse";
    case WakeSource::Rtc:
      return "rtc";
    case WakeSource::UploadButton:
      return "upload-button";
    default:
      return "none";
  }
}

WakeSource resolveWakeSource(esp_sleep_wakeup_cause_t cause) {
  const bool uploadPressed = digitalRead(pins::UploadButtonPin) == LOW;
  if (uploadPressed) {
    return WakeSource::UploadButton;
  }

  if (cause != ESP_SLEEP_WAKEUP_GPIO) {
    return WakeSource::None;
  }

  const bool pulseHigh = digitalRead(static_cast<uint8_t>(pins::PulseWakePin)) == HIGH;
  const bool rtcLow = digitalRead(static_cast<uint8_t>(pins::RtcWakePin)) == LOW;

  if (pulseHigh) {
    return WakeSource::Pulse;
  }
  if (rtcLow) {
    return WakeSource::Rtc;
  }
  return WakeSource::None;
}

void configurePins() {
  pinMode(pins::UploadButtonPin, INPUT_PULLUP);
  pinMode(static_cast<uint8_t>(pins::PulseWakePin), INPUT);
  pinMode(static_cast<uint8_t>(pins::RtcWakePin), INPUT_PULLUP);
  pinMode(pins::AwakeLedPin, OUTPUT);
  digitalWrite(pins::AwakeLedPin, HIGH);
}

void enterDeepSleep() {
  if (!config::EnableDeepSleep) {
    logEvent("deep sleep disabled: staying awake");
    if (config::KeepWifiConnectedWhenAwake) {
      upload::ensureWifiConnected();
    }
    return;
  }

  logEvent("entering deep sleep");
  WiFi.mode(WIFI_OFF);
  digitalWrite(pins::AwakeLedPin, LOW);

  // Wait for pulse pin to go LOW so we don't immediately re-wake and
  // double-count the same pulse (GPIO wakeup is level-triggered on ESP32-C3).
  {
    const uint32_t settleStart = millis();
    while (digitalRead(static_cast<uint8_t>(pins::PulseWakePin)) == HIGH &&
           millis() - settleStart < config::PulseDebounceMs * 4) {
      delay(1);
    }
  }

  // Only GPIOs 0-5 support deep sleep wakeup on ESP32-C3. The upload button
  // on D1/GPIO3 is now included so a button press can wake the device.
  esp_deep_sleep_enable_gpio_wakeup(1ULL << static_cast<uint32_t>(pins::UploadButtonWakePin), ESP_GPIO_WAKEUP_GPIO_LOW);
  esp_deep_sleep_enable_gpio_wakeup(1ULL << static_cast<uint32_t>(pins::RtcWakePin), ESP_GPIO_WAKEUP_GPIO_LOW);
  esp_deep_sleep_enable_gpio_wakeup(1ULL << static_cast<uint32_t>(pins::PulseWakePin), ESP_GPIO_WAKEUP_GPIO_HIGH);

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

void attachAwakePulseInterrupt() {
  if (awakePulseInterruptAttached) {
    return;
  }

  awakePulseCount = 0;
  lastPulseRiseMs = millis();
  attachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(pins::PulseWakePin)), onPulseRise, RISING);
  awakePulseInterruptAttached = true;
  logEvent("pulse interrupt attached");
}

void detachAwakePulseInterrupt() {
  if (!awakePulseInterruptAttached) {
    return;
  }

  detachInterrupt(digitalPinToInterrupt(static_cast<uint8_t>(pins::PulseWakePin)));
  awakePulseInterruptAttached = false;
  logEvent("pulse interrupt detached");
}

bool sleepMakesSenseAfterPulse(uint32_t timestamp) {
  if (timestamp == 0 || lastAcceptedPulseWakeUnix == 0 || timestamp <= lastAcceptedPulseWakeUnix) {
    return true;
  }

  const uint32_t intervalMs = (timestamp - lastAcceptedPulseWakeUnix) * 1000UL;
  return intervalMs > config::PulseAwakeThresholdMs;
}

bool isPulseRewake(uint32_t timestamp) {
  const bool pulseStillHigh = digitalRead(static_cast<uint8_t>(pins::PulseWakePin)) == HIGH;
  const bool repeatedTimestamp = timestamp > 0 && lastPulseWakeUnix > 0 && timestamp <= lastPulseWakeUnix;

  if (!pulseStillHigh) {
    return false;
  }

  if (repeatedTimestamp) {
    logEvent("pulse re-wake suppressed: pin still high");
    return true;
  }

  return false;
}

uint32_t countAwakeUntilQuiet() {
  awakePulseCount = 0;
  lastPulseRiseMs = millis();

  const uint32_t settleStart = millis();
  while (digitalRead(static_cast<uint8_t>(pins::PulseWakePin)) == HIGH &&
         millis() - settleStart < config::PulseDebounceMs * 4) {
    delay(1);
  }

  attachAwakePulseInterrupt();

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

  detachAwakePulseInterrupt();
  return awakePulseCount;
}

void handlePulseWake(uint32_t timestamp) {
  logEvent("pulse wake");

  // Suppress immediate re-wakes while the pulse line is still held high.
  // This avoids double-counting the same physical pulse when the ESP32-C3
  // wakes again before the line has returned low.
  if (isPulseRewake(timestamp)) {
    return;
  }

  const bool sleepNow = sleepMakesSenseAfterPulse(timestamp);
  lastPulseWakeUnix = timestamp;
  lastAcceptedPulseWakeUnix = timestamp;

  uint32_t pulses = 1;
  if (!sleepNow) {
    logEvent("frequent pulses: counting while awake");
    pulses += countAwakeUntilQuiet();
  }

  if (storage::addPulses(timestamp, pulses) && config::EnableSerialLogs) {
    Serial.printf("pulse stored count=%lu timestamp=%lu\n",
                  static_cast<unsigned long>(pulses),
                  static_cast<unsigned long>(timestamp));
  }
}

void handleRtcWake(uint32_t timestamp) {
  logEvent("rtc wake");
  // Perform full RTC initialization including alarm cleanup for RTC wakes.
  rtc_clock::begin();

  if (config::RtcWakeIntervalSeconds < 86400) {
    digitalWrite(pins::AwakeLedPin, LOW);
    delay(50);
    digitalWrite(pins::AwakeLedPin, HIGH);
  }

  const auto reading = battery::sample();
  if (config::EnableSerialLogs) {
    Serial.printf("rtc roll battery=%.2fV pct=%u\n", reading.volts, reading.percent);
  }
  storage::rollCurrentPeriod(timestamp, static_cast<uint16_t>(reading.volts * 1000.0f));
  rtc_clock::scheduleNextWakeAlarm();
}

void handleUploadWake() {
  logEvent("upload button wake");
  if (!uploadButtonPressed()) {
    logEvent("upload button debounce rejected");
    return;
  }

  logEvent("pre-roll");
  storage::dump(Serial);
  storage::rollCurrentPeriod(currentTimestamp(),
                             static_cast<uint16_t>(battery::sample().volts * 1000.0f));
  logEvent("post-roll");
  storage::dump(Serial);

  storage::UploadBatch batch{};
  if (!storage::loadUploadBatch(batch)) {
    logEvent("failed to load upload batch");
    return;
  }

  const auto reading = battery::sample();
  if (config::EnableSerialLogs) {
    Serial.printf("upload batch records=%u battery=%.2fV pct=%u\n",
                  batch.count,
                  reading.volts,
                  reading.percent);
  }
  const auto result = upload::sendBatch(batch, reading);
  if (config::EnableSerialLogs) {
    Serial.printf("upload result=%s records=%u\n", upload::resultName(result), batch.count);
  }

  if (result == upload::Result::Success) {
    storage::markSyncedThrough(batch.newestSequence);
    logEvent("upload marked records synced");
    upload::checkFirmwareUpdate();
  }
}

void handleDiagnosticsBoot() {
  logEvent("diagnostics boot");
  storage::dump(Serial);
  const auto reading = battery::sample();
  Serial.printf("battery=%.2fV pct=%u\n", reading.volts, reading.percent);

  Serial.println("Diagnostics REPL. Commands: dump, clear, status, reboot");
  while (true) {
    if (Serial.available()) {
      String cmd = Serial.readStringUntil('\n');
      cmd.trim();
      if (cmd == "dump") {
        storage::dump(Serial);
      } else if (cmd == "clear") {
        storage::clear();
        Serial.println("storage cleared");
      } else if (cmd == "status") {
        const auto r = battery::sample();
        Serial.printf("battery=%.2fV pct=%u wifi=%s\n", r.volts, r.percent, WiFi.status() == WL_CONNECTED ? "connected" : "disconnected");
      } else if (cmd == "reboot") {
        ESP.restart();
      } else if (cmd.length() > 0) {
        Serial.println("unknown command");
      }
    }
    
    // flash LED to indicate alive in diagnostics
    static uint32_t lastLed = 0;
    if (millis() - lastLed > 1000) {
      lastLed = millis();
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
    }
    
    delay(10);
  }
}

uint32_t currentTimestamp() {
  if (rtcClockAvailable) {
    return rtc_clock::nowUnix();
  }
  return millis() / 1000UL;
}

void flushAwakePulses() {
  if (config::EnableDeepSleep || millis() - lastAwakePulseFlushMs < config::AwakePulseFlushMs) {
    return;
  }

  noInterrupts();
  const uint32_t pulses = awakePulseCount;
  awakePulseCount = 0;
  interrupts();

  lastAwakePulseFlushMs = millis();
  if (pulses == 0) {
    return;
  }

  const uint32_t timestamp = currentTimestamp();
  if (storage::addPulses(timestamp, pulses) && config::EnableSerialLogs) {
    Serial.printf("awake pulse flush count=%lu timestamp=%lu\n",
                  static_cast<unsigned long>(pulses),
                  static_cast<unsigned long>(timestamp));
  }
}

void keepWifiConnected() {
  if (!config::KeepWifiConnectedWhenAwake ||
      millis() - lastWifiCheckMs < config::WifiReconnectIntervalMs) {
    return;
  }

  lastWifiCheckMs = millis();
  if (WiFi.status() != WL_CONNECTED) {
    logEvent("wifi disconnected: reconnecting");
    upload::ensureWifiConnected();
  }
}

void pollAwakeControls() {
  static bool uploadWasPressed = false;
  static bool rtcWasLow = false;

  const bool uploadPressed = digitalRead(pins::UploadButtonPin) == LOW;
  if (uploadPressed && !uploadWasPressed) {
    handleUploadWake();
  }
  uploadWasPressed = uploadPressed;

  const bool rtcLow = digitalRead(static_cast<uint8_t>(pins::RtcWakePin)) == LOW;
  if (rtcLow && !rtcWasLow) {
    handleRtcWake(currentTimestamp());
  }
  rtcWasLow = rtcLow;
}

} // namespace

void setup() {
  // Cancel OTA rollback so the firmware can boot normally after a valid update.
  esp_ota_mark_app_valid_cancel_rollback();

  if (config::EnableSerialLogs) {
    // Start serial logging to provide boot-time diagnostics.
    Serial.begin(115200);
    delay(300);
  }

  // Configure the GPIO pins used for wake sources, buttons, and LED status.
  configurePins();
  // Initialize the I2C bus for attached peripherals.
  Wire.begin(pins::I2cSdaPin, pins::I2cSclPin);
  // Initialize battery monitoring so the device can report power state.
  battery::begin();

  // Initialize the RTC and storage subsystems before handling boot behavior.
  // Use time-only initialization for leaner pulse wakeups; full init with alarm
  // cleanup will be done for RTC wakes.
  const bool rtcOk = rtc_clock::beginTimeOnly();
  const bool storageOk = storage::begin();
  rtcClockAvailable = rtcOk;
  storageAvailable = storageOk;
  if (!rtcOk) {
    logLine("rtc init failed; using fallback timestamps");
  }
  if (!storageOk) {
    logLine("storage init failed; persistence disabled for this boot");
  }

  // Read the current timestamp and wake cause to decide how the boot should proceed.
  const uint32_t timestamp = currentTimestamp();
  const esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  const WakeSource wakeSource = resolveWakeSource(cause);

  if (config::EnableSerialLogs) {
    Serial.printf("boot cause=%d wake=%s rtc_available=%d storage_available=%d\n",
                  static_cast<int>(cause),
                  wakeSourceName(wakeSource),
                  rtcClockAvailable ? 1 : 0,
                  storageAvailable ? 1 : 0);
  }

  // Handle a wake caused by the pulse input before returning to deep sleep.
  if (wakeSource == WakeSource::Pulse) {
    handlePulseWake(timestamp);
    enterDeepSleep();
    return;
  }

  // Handle a wake caused by the RTC before returning to deep sleep.
  if (wakeSource == WakeSource::Rtc) {
    handleRtcWake(timestamp);
    enterDeepSleep();
    return;
  }

  // Handle a wake caused by the upload button before returning to deep sleep.
  if (wakeSource == WakeSource::UploadButton) {
    handleUploadWake();
    enterDeepSleep();
    return;
  }

  // Run the boot diagnostics and schedule the next wake alarm.
  handleDiagnosticsBoot();
  if (rtcClockAvailable) {
    rtc_clock::scheduleNextWakeAlarm();
  }

  // Enter deep sleep for normal boots unless the device should stay awake on USB.
  if (!config::StayAwakeOnUsbBoot) {
    enterDeepSleep();
    return;
  }

  // Keep the device awake and listening for pulses when deep sleep is disabled.
  if (!config::EnableDeepSleep) {
    attachAwakePulseInterrupt();
    if (config::KeepWifiConnectedWhenAwake) {
      upload::ensureWifiConnected();
      upload::syncRtcFromNetwork();
    }
  }
}

void loop() {
  if (!config::EnableDeepSleep) {
    flushAwakePulses();
    pollAwakeControls();
    keepWifiConnected();
  }
  delay(50);
}

