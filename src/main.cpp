#include <Arduino.h>
#include <Wire.h>
#include <esp_sleep.h>
#include <esp_system.h>
#include <esp_ota_ops.h>
#include <WiFi.h>
#include <freertos/FreeRTOS.h>
#include <freertos/timers.h>

#include "battery.h"
#include "config.h"
#include "pins.h"
#include "rtc_clock.h"
#include "storage.h"
#include "upload.h"
#include "awake_led.h"

namespace {

enum class WakeSource {
  None,
  Pulse,
  Rtc,
  UploadButton,
};

enum class UploadPressKind {
  Short,
  Long,
};

RTC_DATA_ATTR uint32_t lastPulseWakeUnix = 0;
RTC_DATA_ATTR uint32_t lastAcceptedPulseWakeUnix = 0;

volatile uint32_t awakePulseCount = 0;
volatile uint32_t lastPulseRiseMs = 0;
volatile bool pulseDetected = false;
uint32_t lastAwakePulseFlushMs = 0;
uint32_t lastWifiCheckMs = 0;
bool awakePulseInterruptAttached = false;
bool rtcClockAvailable = false;
bool storageAvailable = false;
bool serialStarted = false;
TimerHandle_t pulseLedOffTimer = nullptr;

AwakeLed awakeLed;

void logLine(const char *message) {
  if (config::EnableSerialLogs && serialStarted) {
    Serial.println(message);
  }
}

void pulseLedOffTimerCallback(TimerHandle_t) {
  digitalWrite(pins::PulseLedPin, LOW);
}

void initPulseLedOffTimer() {
  if ((config::LedEventMask & config::led_event::Pulse) != 0) {
    return;
  }
  if (pulseLedOffTimer != nullptr) {
    return;
  }
  // One-shot: ISR turns the LED on and resets this 100 ms off deadline so the
  // flash completes even when loop()/upload blocks.
  pulseLedOffTimer = xTimerCreate("pulse_led_off", pdMS_TO_TICKS(100), pdFALSE, nullptr,
                                  pulseLedOffTimerCallback);
}

void IRAM_ATTR schedulePulseLedOffFromIsr() {
  if (pulseLedOffTimer == nullptr) {
    return;
  }
  BaseType_t higherPriorityTaskWoken = pdFALSE;
  xTimerResetFromISR(pulseLedOffTimer, &higherPriorityTaskWoken);
  if (higherPriorityTaskWoken == pdTRUE) {
    portYIELD_FROM_ISR();
  }
}

uint32_t currentTimestamp();
void flushAwakePulses(bool force = false);
void enterStayAwakeMode();
void initWakePinsAndLed();
void initSerialIfNeeded(bool withLogDelay);
void initSubsystems(bool needFullRtc);
String formatUtcTimestamp(uint32_t timestamp);
String formatHumanUtcTimestamp(uint32_t timestamp);

bool debugHostConnected() {
  // XIAO ESP32-C3 uses HWCDC (USB-serial-JTAG). Stay awake only when USB is
  // plugged and a host has the CDC port open — not merely because Serial.begin ran.
  return serialStarted && Serial.isPlugged() && Serial.isConnected();
}

bool usbPowered() {
  // USB VBUS present (CDC plugged). Wall chargers without a host still unlock
  // via BatteryRadioUnlockVolts hysteresis.
  return Serial.isPlugged();
}

bool shouldStayAwake() {
  if (storage::protectionLocked() && !usbPowered()) {
    return false;
  }
  return debugHostConnected() || storage::stayAwakeBoot();
}

void logEvent(const char *event) {
  if (config::EnableSerialLogs && serialStarted) {
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
  if (cause != ESP_SLEEP_WAKEUP_GPIO) {
    return WakeSource::None;
  }

  // Human button presses last long enough to sample after wake.
  if (digitalRead(pins::UploadButtonPin) == LOW) {
    return WakeSource::UploadButton;
  }

  if (digitalRead(pins::RtcWakePin) == LOW) {
    return WakeSource::Rtc;
  }

  // S0 meter pulses are ~3–50 ms; deep-sleep wake + boot is usually longer, so
  // PulseWakePin is often already HIGH. Default GPIO wake to Pulse.
  return WakeSource::Pulse;
}

void initWakePinsAndLed() {
  pinMode(pins::UploadButtonPin, INPUT_PULLUP);
  pinMode(pins::PulseWakePin, INPUT_PULLUP);
  pinMode(pins::RtcWakePin, INPUT_PULLUP);
  pinMode(pins::PulseLedPin, OUTPUT);
  digitalWrite(pins::PulseLedPin, LOW);
  initPulseLedOffTimer();
  awakeLed.init();
  if (config::EnableDeepSleep) {
    awakeLed.setMode(AwakeLed::Mode::WakeFromDeepSleep);
  } else {
    awakeLed.setMode(AwakeLed::Mode::AlwaysAwake);
  }
  awakeLed.setAwake();
}

void initSerialIfNeeded(bool withLogDelay) {
  if (serialStarted) {
    return;
  }
  Serial.begin(115200);
  serialStarted = true;
  if (withLogDelay && config::EnableSerialLogs) {
    delay(300);
  }
}

void initSubsystems(bool needFullRtc) {
  Wire.begin(pins::I2cSdaPin, pins::I2cSclPin);
  battery::begin();
  const bool rtcOk = needFullRtc ? rtc_clock::begin() : rtc_clock::beginTimeOnly();
  const bool storageOk = storage::begin();
  rtcClockAvailable = rtcOk;
  storageAvailable = storageOk;
  if (!rtcOk) {
    logLine("rtc init failed; using fallback timestamps");
  }
  if (!storageOk) {
    logLine("storage init failed; persistence disabled for this boot");
  }
}

// GPIO deep-sleep wakeup is level-triggered on ESP32-C3. If we arm the upload
// button while it is still held (or bouncing), sleep immediately re-wakes and
// repeats the upload cycle for the duration of a long press.
void waitForUploadButtonRelease() {
  if (digitalRead(pins::UploadButtonPin) != LOW) {
    return;
  }

  logEvent("waiting for upload button release before sleep");
  while (true) {
    while (digitalRead(pins::UploadButtonPin) == LOW) {
      delay(10);
    }

    // Require a stable HIGH so contact bounce does not re-arm a wake.
    const uint32_t releasedAt = millis();
    bool bounced = false;
    while (millis() - releasedAt < config::PulseDebounceMs) {
      if (digitalRead(pins::UploadButtonPin) == LOW) {
        bounced = true;
        break;
      }
      delay(1);
    }
    if (!bounced) {
      logEvent("upload button released");
      return;
    }
  }
}

void enterDeepSleep() {
  if (!config::EnableDeepSleep) {
    logEvent("deep sleep disabled: staying awake");
    if (config::KeepWifiConnectedWhenAwake && !storage::protectionLocked()) {
      upload::ensureWifiConnected();
    }
    return;
  }

  const bool protection = storage::protectionLocked();
  logEvent(protection ? "entering deep sleep (button-only protection)"
                      : "entering deep sleep");
  if (pulseLedOffTimer != nullptr) {
    xTimerStop(pulseLedOffTimer, 0);
  }
  digitalWrite(pins::PulseLedPin, LOW);
  pinMode(pins::PulseLedPin, INPUT_PULLDOWN);
  awakeLed.setSleep();
  WiFi.mode(WIFI_OFF);

  if (!protection) {
    // Wait for pulse pin to go HIGH so we don't immediately re-wake and
    // double-count the same pulse (GPIO wakeup is level-triggered on ESP32-C3).
    const uint32_t settleStart = millis();
    while (digitalRead(pins::PulseWakePin) == LOW &&
           millis() - settleStart < config::PulseDebounceMs * 4) {
      delay(1);
    }
  }

  waitForUploadButtonRelease();

  // Only GPIOs 0-5 support deep sleep wakeup on ESP32-C3.
  esp_deep_sleep_enable_gpio_wakeup(1ULL << pins::UploadButtonPin, ESP_GPIO_WAKEUP_GPIO_LOW);
  if (!protection) {
    esp_deep_sleep_enable_gpio_wakeup(1ULL << pins::RtcWakePin, ESP_GPIO_WAKEUP_GPIO_LOW);
    esp_deep_sleep_enable_gpio_wakeup(1ULL << pins::PulseWakePin, ESP_GPIO_WAKEUP_GPIO_LOW);
  }

  if (config::EnableSerialLogs) {
    Serial.flush();
  }
  esp_deep_sleep_start();
}

void enterProtectionSleep() {
  if (rtcClockAvailable) {
    rtc_clock::disableWakeAlarm();
  }
  enterDeepSleep();
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
    pulseDetected = true;
    if ((config::LedEventMask & config::led_event::Pulse) == 0) {
      digitalWrite(pins::PulseLedPin, HIGH);
      schedulePulseLedOffFromIsr();
    }
  }
}

void attachAwakePulseInterrupt() {
  if (awakePulseInterruptAttached) {
    return;
  }

  awakePulseCount = 0;
  lastPulseRiseMs = millis();
  attachInterrupt(digitalPinToInterrupt(pins::PulseWakePin), onPulseRise, FALLING);
  awakePulseInterruptAttached = true;
  logEvent("pulse interrupt attached");
}

void detachAwakePulseInterrupt() {
  if (!awakePulseInterruptAttached) {
    return;
  }

  detachInterrupt(digitalPinToInterrupt(pins::PulseWakePin));
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

uint32_t countAwakeUntilQuiet() {
  awakePulseCount = 0;
  lastPulseRiseMs = millis();

  const uint32_t settleStart = millis();
  while (digitalRead(pins::PulseWakePin) == LOW &&
         millis() - settleStart < config::PulseDebounceMs * 4) {
    delay(1);
  }

  attachAwakePulseInterrupt();

  uint32_t lastCount = 0;
  uint32_t quietSince = millis();

  while (true) {
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

  if ((config::LedEventMask & config::led_event::Pulse) == 0) {
    digitalWrite(pins::PulseLedPin, HIGH);
    delay(100);
    digitalWrite(pins::PulseLedPin, LOW);
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
  awakeLed.blink();
  // Perform full RTC initialization including alarm cleanup for RTC wakes.
  rtc_clock::begin();

  const auto reading = battery::sampleForRecord();
  const uint16_t hotBefore = storage::currentPulses();
  const bool rolled = storage::rollCurrentPeriod(
      timestamp, static_cast<uint16_t>(reading.volts * 1000.0f));
  if (config::EnableSerialLogs) {
    if (hotBefore == 0) {
      Serial.printf(
          "rtc roll hot_pulses=0 battery=%.3fV pct=%u timestamp=%lu (%s) (no append)\n",
          reading.volts,
          reading.percent,
          static_cast<unsigned long>(timestamp),
          formatUtcTimestamp(timestamp).c_str());
    } else if (rolled) {
      Serial.printf(
          "rtc roll hot_pulses=%u -> appended battery=%.3fV pct=%u timestamp=%lu (%s)\n",
          static_cast<unsigned>(hotBefore),
          reading.volts,
          reading.percent,
          static_cast<unsigned long>(timestamp),
          formatUtcTimestamp(timestamp).c_str());
    } else {
      Serial.printf(
          "rtc roll hot_pulses=%u append failed storage_ok=%d battery=%.3fV pct=%u timestamp=%lu (%s)\n",
          static_cast<unsigned>(hotBefore),
          storage::available() ? 1 : 0,
          reading.volts,
          reading.percent,
          static_cast<unsigned long>(timestamp),
          formatUtcTimestamp(timestamp).c_str());
    }
  }

  if (battery::evaluateProtectionLock(reading.volts, usbPowered())) {
    rtc_clock::disableWakeAlarm();
    return;
  }
  rtc_clock::scheduleNextWakeAlarm();
}

void handleUploadWake(bool force = false) {
  logEvent(force ? "forced upload" : "upload button wake");
  if (!force && !uploadButtonPressed()) {
    logEvent("upload button debounce rejected");
    return;
  }

  const bool pulseInterruptWasAttached = awakePulseInterruptAttached;
  attachAwakePulseInterrupt();
  awakeLed.startPulseBlink();

  // Flush RAM awake pulses into the open period so they roll into this upload.
  flushAwakePulses(true);

  logEvent("pre-roll");
  const auto reading = battery::sampleForRecord();
  storage::rollCurrentPeriod(currentTimestamp(),
                             static_cast<uint16_t>(reading.volts * 1000.0f));
  logEvent("post-roll");

  if (battery::evaluateProtectionLock(reading.volts, usbPowered())) {
    logEvent("upload blocked: protection lock");
    flushAwakePulses(true);
    if (!pulseInterruptWasAttached) detachAwakePulseInterrupt();
    awakeLed.rapidErrorBlink();
    upload::disconnectWifiIfAllowed();
    awakeLed.setAwake();
    return;
  }

  bool includeBattery = true;
  bool uploadSucceeded = true;
  bool uploadedRecords = false;

  if (!upload::ensureWifiConnected()) {
    logEvent("upload wifi failed before batch");
    uploadSucceeded = false;
  } else {
    upload::syncRtcFromNetwork();
    // One upload_session_id for every POST in this wake (16 random bytes as hex).
    char uploadSessionId[33];
    static const char kHex[] = "0123456789abcdef";
    for (int i = 0; i < 16; ++i) {
      const uint8_t b = static_cast<uint8_t>(esp_random() & 0xffu);
      uploadSessionId[i * 2] = kHex[(b >> 4) & 0x0f];
      uploadSessionId[i * 2 + 1] = kHex[b & 0x0f];
    }
    uploadSessionId[32] = '\0';

    upload::HttpSession session;
    while (true) {
      storage::UploadBatch batch{};
      if (!storage::loadUploadBatch(batch)) {
        logEvent("failed to load upload batch");
        uploadSucceeded = false;
        break;
      }
      storage::attachPendingProtectionErrors(batch);

      if (config::EnableSerialLogs) {
        if (includeBattery) {
          Serial.printf("upload batch records=%u errors=%u battery=%.3fV pct=%u\n",
                        batch.count, batch.errorCount, reading.volts, reading.percent);
        } else {
          Serial.printf("upload batch records=%u errors=%u battery=omitted\n",
                        batch.count, batch.errorCount);
        }
      }
      const bool lastBatch = !batch.truncated;
      const auto result =
          session.post(batch, includeBattery ? &reading : nullptr, uploadSessionId, lastBatch);
      includeBattery = false;
      if (config::EnableSerialLogs) {
        Serial.printf("upload result=%s records=%u errors=%u last_batch=%d\n",
                      upload::resultName(result), batch.count, batch.errorCount,
                      lastBatch ? 1 : 0);
      }
      if (result != upload::Result::Success) {
        uploadSucceeded = false;
        break;
      }
      storage::clearPendingProtectionErrors();
      if (batch.count > 0) {
        uploadedRecords = true;
        storage::markSyncedThrough(batch.newestSequence);
        logEvent("upload marked records synced");
      }
      // Empty heartbeat or final partial batch: one POST is enough unless truncated.
      if (batch.count == 0 || !batch.truncated) {
        break;
      }
    }
    session.end();
  }

  if (uploadedRecords) {
    storage::compactRecords();
  }

  flushAwakePulses(true);
  if (!pulseInterruptWasAttached) detachAwakePulseInterrupt();
  if (uploadSucceeded) {
    if (uploadedRecords) {
      upload::checkFirmwareUpdate();
    }
  } else {
    awakeLed.rapidErrorBlink();
  }
  upload::disconnectWifiIfAllowed();
  // Upload blink helpers may leave the pin low; restore while still awake.
  // enterDeepSleep() calls setSleep() when actually sleeping.
  awakeLed.setAwake();
}

// Long-press toggles stay-awake. Returns the new flag value.
bool handleStayAwakeToggle() {
  const bool enabled = !storage::stayAwakeBoot();
  storage::setStayAwakeBoot(enabled);
  if (config::EnableSerialLogs && serialStarted) {
    Serial.printf("StayAwakeBoot=%s\n", enabled ? "true" : "false");
  }
  logEvent(enabled ? "stay awake enabled" : "stay awake disabled");
  if (enabled) {
    awakeLed.setOn();
    awakeLed.doubleBlink();
    awakeLed.setAwake();
  } else {
    awakeLed.rapidErrorBlink();
  }
  return enabled;
}

// Classify upload button from deep-sleep wake. Call immediately after pins/LED —
// before Serial delay and peripheral init — so short taps are not lost.
UploadPressKind classifyUploadPressFromWake() {
  if (digitalRead(pins::UploadButtonPin) != LOW) {
    logEvent("upload wake: button already released, short press");
    return UploadPressKind::Short;
  }

  const uint32_t pressedAt = millis();
  while (true) {
    if (digitalRead(pins::UploadButtonPin) != LOW) {
      const uint32_t releasedAt = millis();
      bool bounced = false;
      while (millis() - releasedAt < config::PulseDebounceMs) {
        if (digitalRead(pins::UploadButtonPin) == LOW) {
          bounced = true;
          break;
        }
        delay(1);
      }
      if (bounced) {
        continue;
      }
      logEvent("upload wake: short press");
      return UploadPressKind::Short;
    }

    if (millis() - pressedAt >= config::UploadLongPressMs) {
      logEvent("upload wake: long press");
      return UploadPressKind::Long;
    }
    delay(10);
  }
}

// Awake-path button handler (diagnostics / poll).
// Returns true when stay-awake remains active after a long-press enable.
bool handleUploadButton(bool force = false) {
  if (force) {
    handleUploadWake(true);
    return false;
  }

  if (!uploadButtonPressed()) {
    logEvent("upload button debounce rejected");
    return false;
  }

  const uint32_t pressedAt = millis();
  while (true) {
    if (digitalRead(pins::UploadButtonPin) != LOW) {
      const uint32_t releasedAt = millis();
      bool bounced = false;
      while (millis() - releasedAt < config::PulseDebounceMs) {
        if (digitalRead(pins::UploadButtonPin) == LOW) {
          bounced = true;
          break;
        }
        delay(1);
      }
      if (bounced) {
        continue;
      }
      handleUploadWake(true);
      return false;
    }

    if (millis() - pressedAt >= config::UploadLongPressMs) {
      logEvent("upload button long press");
      const bool enabled = handleStayAwakeToggle();
      waitForUploadButtonRelease();
      if (!enabled) {
        enterDeepSleep();
        return false;
      }
      return true;
    }
    delay(10);
  }
}

void dumpUploadJson() {
  Serial.printf("open hot: storage_ok=%d hot_pulses=%u hot_start=%lu\n",
                storage::available() ? 1 : 0,
                static_cast<unsigned>(storage::currentPulses()),
                static_cast<unsigned long>(storage::currentPeriodStart()));
  Serial.println("note: JSON readings are rolled LittleFS only; open hot is not included until RTC roll or upload");

  storage::UploadBatch batch{};
  if (!storage::loadUploadBatch(batch)) {
    Serial.println("failed to load upload batch");
    return;
  }
  const auto reading = battery::sample();
  Serial.println(upload::buildBody(batch, &reading));
}

void fillSyntheticRecords(uint32_t count) {
  if (!storage::available()) {
    Serial.println("fill failed: storage unavailable");
    return;
  }

  flushAwakePulses(true);

  const auto reading = battery::sample();
  const uint16_t batteryMv = static_cast<uint16_t>(reading.volts * 1000.0f);
  const uint32_t now = currentTimestamp();
  if (storage::currentPulses() > 0) {
    if (!storage::rollCurrentPeriod(now, batteryMv)) {
      Serial.println("fill failed: could not roll open period");
      return;
    }
  }

  const uint32_t interval = config::RtcWakeIntervalSeconds;
  const uint32_t base = now > (count * interval) ? now - (count * interval) : 0;
  // Zero-pulse roll sets hot periodStart to base without appending.
  if (!storage::rollCurrentPeriod(base, batteryMv)) {
    Serial.println("fill failed: could not align period start");
    return;
  }

  uint32_t filled = 0;
  for (uint32_t i = 0; i < count; ++i) {
    const uint16_t pulses = static_cast<uint16_t>(random(1, 101));
    storage::addPulses(base + i * interval, pulses);
    if (!storage::rollCurrentPeriod(base + (i + 1) * interval, batteryMv)) {
      Serial.printf("fill failed after %lu records\n",
                    static_cast<unsigned long>(filled));
      return;
    }
    ++filled;
  }
  Serial.printf("filled %lu records\n", static_cast<unsigned long>(filled));
}

void handleDiagnosticsBoot() {
  logEvent("diagnostics boot");
  storage::hexdump(Serial);
  const auto reading = battery::sample();
  Serial.printf("battery=%.3fV pct=%u\n", reading.volts, reading.percent);
  if (battery::evaluateProtectionLock(reading.volts, usbPowered())) {
    logEvent("diagnostics: protection lock — button-only sleep");
    enterProtectionSleep();
    return;
  }

  Serial.println(
      "Diagnostics REPL. Commands: d[ump], h[exdump], clear, status, t[ime], "
      "f[ill] [N], upload, reboot, x[sleep]");
  String cmd = "";
  static bool uploadWasLow = false;
  static bool rtcWasLow = false;
  while (true) {
    if (pulseDetected) {
      pulseDetected = false;
      noInterrupts();
      const uint32_t count = awakePulseCount;
      interrupts();
      char buf[64];
      snprintf(buf, sizeof(buf), "pulse detected count=%lu", static_cast<unsigned long>(count));
      logEvent(buf);
    }

    flushAwakePulses();

    const bool uploadLow = digitalRead(pins::UploadButtonPin) == LOW;
    if (uploadLow && !uploadWasLow) {
      logEvent("upload button detected");
      const bool stayAfterLongPress = handleUploadButton();
      if (storage::protectionLocked()) {
        enterProtectionSleep();
        return;
      }
      if (!stayAfterLongPress && !shouldStayAwake()) {
        enterDeepSleep();
      }
    }
    // Re-read after handling: press may have been released inside handleUploadButton.
    uploadWasLow = digitalRead(pins::UploadButtonPin) == LOW;

    const bool rtcLow = digitalRead(pins::RtcWakePin) == LOW;
    if (rtcLow && !rtcWasLow) {
      logEvent("rtc interrupt detected");
      handleRtcWake(currentTimestamp());
      if (storage::protectionLocked()) {
        enterProtectionSleep();
        return;
      }
    }
    rtcWasLow = rtcLow;

    if (Serial.available()) {
      const char c = Serial.read();
      if (c == '\n' || c == '\r') {
        cmd.trim();
        Serial.println();
        if (cmd.length() > 0) {
          const char first = cmd.charAt(0);
          if (cmd == "t" || cmd == "time") {
            Serial.printf("current time: %s\n",
                          formatHumanUtcTimestamp(currentTimestamp()).c_str());
          } else if (first == 'd') {
            dumpUploadJson();
          } else if (first == 'h') {
            storage::hexdump(Serial);
          } else if (first == 'c') {
            storage::clear();
            Serial.println("storage cleared");
          } else if (first == 'f') {
            uint32_t count = 100;
            const int space = cmd.indexOf(' ');
            if (space > 0) {
              const long parsed = cmd.substring(space + 1).toInt();
              if (parsed <= 0) {
                Serial.println("usage: f[ill] [N]  (default 100, max 500)");
              } else {
                count = parsed > 500 ? 500 : static_cast<uint32_t>(parsed);
                fillSyntheticRecords(count);
              }
            } else {
              fillSyntheticRecords(count);
            }
          } else if (first == 's') {
            const auto r = battery::sample();
            const bool pulseLow = digitalRead(pins::PulseWakePin) == LOW;
            const uint32_t now = currentTimestamp();
            const uint32_t nextAlarm = rtcClockAvailable ? rtc_clock::getNextAlarmUnix() : 0;

            time_t raw = now;
            tm timeinfo{};
            gmtime_r(&raw, &timeinfo);
            char nowIso[25];
            strftime(nowIso, sizeof(nowIso), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);

            String nextAlarmIso = nextAlarm > 0 ? String("") : String("none");
            if (nextAlarm > 0) {
              time_t rawNext = nextAlarm;
              tm timeinfoNext{};
              gmtime_r(&rawNext, &timeinfoNext);
              char nextAlarmBuf[25];
              strftime(nextAlarmBuf, sizeof(nextAlarmBuf), "%Y-%m-%dT%H:%M:%SZ", &timeinfoNext);
              nextAlarmIso = String(nextAlarmBuf);
            }

            Serial.printf("battery=%.3fV pct=%u adc_cal=%s ok=%d wifi=%s pulse=%s count=%lu\n",
                          r.volts, r.percent,
                          battery::calibrationSource(),
                          battery::calibrationOk() ? 1 : 0,
                          WiFi.status() == WL_CONNECTED ? "connected" : "disconnected",
                          pulseLow ? "LOW" : "HIGH",
                          static_cast<unsigned long>(awakePulseCount));
            Serial.printf("storage_ok=%d unsynced=%lu hot_pulses=%u hot_start=%lu awake_count=%lu\n",
                          storage::available() ? 1 : 0,
                          static_cast<unsigned long>(storage::unsyncedCount()),
                          static_cast<unsigned>(storage::currentPulses()),
                          static_cast<unsigned long>(storage::currentPeriodStart()),
                          static_cast<unsigned long>(awakePulseCount));
            Serial.printf("protection=%d reset_reason=%d usb_plugged=%d\n",
                          storage::protectionLocked() ? 1 : 0,
                          static_cast<int>(esp_reset_reason()),
                          usbPowered() ? 1 : 0);
            Serial.printf("inputs upload=%s pulse=%s rtc=%s pulse_led=%s awake_led=%s\n",
                          digitalRead(pins::UploadButtonPin) == LOW ? "LOW" : "HIGH",
                          digitalRead(pins::PulseWakePin) == LOW ? "LOW" : "HIGH",
                          digitalRead(pins::RtcWakePin) == LOW ? "LOW" : "HIGH",
                          digitalRead(pins::PulseLedPin) == HIGH ? "HIGH" : "LOW",
                          awakeLed.isFull() ? "FULL" : (awakeLed.isOn() ? "PWM" : "OFF"));
            Serial.printf("time=%s next_alarm=%s\n", nowIso, nextAlarmIso.c_str());
            if (battery::evaluateProtectionLock(r.volts, usbPowered())) {
              logEvent("status: protection lock — button-only sleep");
              enterProtectionSleep();
              return;
            }
          } else if (first == 'u') {
            logEvent("upload triggered");
            handleUploadButton(true);
            if (storage::protectionLocked()) {
              enterProtectionSleep();
              return;
            }
          } else if (first == 'r') {
            ESP.restart();
          } else if (first == 'x') {
            storage::setStayAwakeBoot(false);
            logEvent("entering deep sleep");
            enterDeepSleep();
          } else {
            Serial.println("unknown command");
          }
        }
        cmd = "";
      } else {
        Serial.write(c);
        cmd += c;
      }
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

String formatUtcTimestamp(uint32_t timestamp) {
  time_t raw = timestamp;
  tm timeinfo{};
  gmtime_r(&raw, &timeinfo);
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(buf);
}

String formatHumanUtcTimestamp(uint32_t timestamp) {
  time_t raw = timestamp;
  tm timeinfo{};
  gmtime_r(&raw, &timeinfo);
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S UTC", &timeinfo);
  return String(buf);
}

void flushAwakePulses(bool force) {
  if (!force && millis() - lastAwakePulseFlushMs < config::AwakePulseFlushMs) {
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
    Serial.printf("awake pulse flush count=%lu timestamp=%lu (%s)\n",
                  static_cast<unsigned long>(pulses),
                  static_cast<unsigned long>(timestamp),
                  formatUtcTimestamp(timestamp).c_str());
  }
}

void keepWifiConnected() {
  if (!config::KeepWifiConnectedWhenAwake || storage::protectionLocked() ||
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
    const bool stayAfterLongPress = handleUploadButton();
    if (storage::protectionLocked()) {
      enterProtectionSleep();
      return;
    }
    if (!stayAfterLongPress && !shouldStayAwake()) {
      enterDeepSleep();
    }
  }
  uploadWasPressed = digitalRead(pins::UploadButtonPin) == LOW;

  const bool rtcLow = digitalRead(pins::RtcWakePin) == LOW;
  if (rtcLow && !rtcWasLow) {
    logEvent("rtc interrupt detected");
    handleRtcWake(currentTimestamp());
    if (storage::protectionLocked()) {
      enterProtectionSleep();
    }
  }
  rtcWasLow = rtcLow;
}

void enterStayAwakeMode() {
  // Keep the device awake and listening for pulses when staying awake.
  attachAwakePulseInterrupt();
  if (config::KeepWifiConnectedWhenAwake && !storage::protectionLocked()) {
    upload::ensureWifiConnected();
    upload::syncRtcFromNetwork();
  }

  // Run the boot diagnostics.
  handleDiagnosticsBoot();
}

void logBootSummary(esp_sleep_wakeup_cause_t cause, WakeSource wakeSource) {
  if (!config::EnableSerialLogs || !serialStarted) {
    return;
  }
  Serial.printf("boot cause=%d wake=%s reset=%d rtc_available=%d storage_available=%d\n",
                static_cast<int>(cause),
                wakeSourceName(wakeSource),
                static_cast<int>(esp_reset_reason()),
                rtcClockAvailable ? 1 : 0,
                storageAvailable ? 1 : 0);
  Serial.printf("stay_awake flash=%d usb=%d protection=%d => %s\n",
                storage::stayAwakeBoot() ? 1 : 0,
                debugHostConnected() ? 1 : 0,
                storage::protectionLocked() ? 1 : 0,
                shouldStayAwake() ? "awake" : "sleep");
}

} // namespace

void setup() {
  esp_ota_mark_app_valid_cancel_rollback();

  // Pins + LED first for immediate feedback and correct wake sampling.
  initWakePinsAndLed();

  const esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  const WakeSource wakeSource = resolveWakeSource(cause);

  // Pulse: leanest path — S0 edge is usually gone; default-to-Pulse already applied.
  if (wakeSource == WakeSource::Pulse) {
    initSubsystems(/*needFullRtc=*/false);
    if (storage::protectionLocked()) {
      // Heal: pulse should not be armed while locked.
      enterProtectionSleep();
      return;
    }
    handlePulseWake(currentTimestamp());
    enterDeepSleep();
    return;
  }

  // RTC: full RTC init for alarm cleanup.
  if (wakeSource == WakeSource::Rtc) {
    initSubsystems(/*needFullRtc=*/true);
    handleRtcWake(currentTimestamp());
    if (storage::protectionLocked()) {
      enterProtectionSleep();
    } else {
      enterDeepSleep();
    }
    return;
  }

  // Upload button: classify short vs long before Serial/LittleFS/I2C delay.
  if (wakeSource == WakeSource::UploadButton) {
    const UploadPressKind kind = classifyUploadPressFromWake();

    initSerialIfNeeded(/*withLogDelay=*/false);
    initSubsystems(/*needFullRtc=*/true);
    logBootSummary(cause, wakeSource);
    battery::noteResetReason();

    const auto reading = battery::sampleForRecord();
    if (battery::evaluateProtectionLock(reading.volts, usbPowered())) {
      waitForUploadButtonRelease();
      awakeLed.rapidErrorBlink();
      enterProtectionSleep();
      return;
    }

    // Restored (or never locked): ensure RTC alarm is armed for normal wakes.
    rtc_clock::begin();
    rtc_clock::scheduleNextWakeAlarm();

    if (kind == UploadPressKind::Long) {
      const bool enabled = handleStayAwakeToggle();
      waitForUploadButtonRelease();
      if (enabled) {
        enterStayAwakeMode();
      } else {
        enterDeepSleep();
      }
      return;
    }

    // Short press → upload.
    handleUploadWake(true);
    if (storage::protectionLocked()) {
      enterProtectionSleep();
      return;
    }
    if (shouldStayAwake()) {
      enterStayAwakeMode();
      return;
    }
    enterDeepSleep();
    return;
  }

  // Cold / non-GPIO boot.
  initSerialIfNeeded(/*withLogDelay=*/true);
  initSubsystems(/*needFullRtc=*/false);
  logBootSummary(cause, wakeSource);
  battery::noteResetReason();

  {
    const auto reading = battery::sampleForRecord();
    if (battery::evaluateProtectionLock(reading.volts, usbPowered())) {
      enterProtectionSleep();
      return;
    }
  }

  if (rtcClockAvailable) {
    rtc_clock::begin();
    rtc_clock::scheduleNextWakeAlarm();
  }

  if (!shouldStayAwake()) {
    enterDeepSleep();
    return;
  }

  enterStayAwakeMode();
}

void loop() {
  if (pulseDetected) {
    pulseDetected = false;
    noInterrupts();
    const uint32_t count = awakePulseCount;
    interrupts();
    char buf[64];
    snprintf(buf, sizeof(buf), "pulse detected count=%lu", static_cast<unsigned long>(count));
    logEvent(buf);
  }

  if (!config::EnableDeepSleep) {
    flushAwakePulses();
    pollAwakeControls();
    keepWifiConnected();
  }
  delay(50);
}

