#pragma once

#include <Arduino.h>
#include <esp_timer.h>
#include "config.h"
#include "pins.h"

class AwakeLed {
public:
  enum class Mode {
    AlwaysAwake,
    WakeFromDeepSleep,
  };

  void init() {
    ledcSetup(PwmChannel, PwmFreqHz, PwmResolutionBits);
    ledcAttachPin(pins::AwakeLedPin, PwmChannel);
    pwmAttached = true;
    writeDuty(DutyOff);
  }

  void setMode(Mode newMode) {
    mode = newMode;
  }

  // Idle-awake indicator: dim PWM.
  void setAwake() {
    stopPulseBlink();
    ensurePwm();
    writeDuty(DutyAwake);
  }

  void setSleep() {
    stopPulseBlink();
    writeDuty(DutyOff);
    if (pwmAttached) {
      ledcDetachPin(pins::AwakeLedPin);
      pwmAttached = false;
    }
    pinMode(pins::AwakeLedPin, INPUT_PULLDOWN);
  }

  // Full brightness — used for long-press feedback.
  void setOn() {
    stopPulseBlink();
    ensurePwm();
    writeDuty(DutyFull);
  }

  void setOff() {
    stopPulseBlink();
    ensurePwm();
    writeDuty(DutyOff);
  }

  // Upload-in-progress: non-blocking toggle DutyAwake ↔ DutyFull every pulseWidthMs.
  void startPulseBlink(uint32_t pulseWidthMs = DefaultUploadPulseMs) {
    stopPulseBlink();
    ensurePwm();
    blinkHigh = true;
    writeDuty(DutyFull);

    if (pulseWidthMs == 0) {
      return;
    }

    const esp_timer_create_args_t args = {
        .callback = &AwakeLed::onPulseBlink,
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "awake_led_blink",
        .skip_unhandled_events = true,
    };
    if (esp_timer_create(&args, &pulseBlinkTimer) != ESP_OK) {
      pulseBlinkTimer = nullptr;
      return;
    }
    if (esp_timer_start_periodic(pulseBlinkTimer,
                                 static_cast<uint64_t>(pulseWidthMs) * 1000ULL) != ESP_OK) {
      esp_timer_delete(pulseBlinkTimer);
      pulseBlinkTimer = nullptr;
    }
  }

  void stopPulseBlink() {
    if (pulseBlinkTimer == nullptr) {
      return;
    }
    esp_timer_stop(pulseBlinkTimer);
    esp_timer_delete(pulseBlinkTimer);
    pulseBlinkTimer = nullptr;
  }

  bool isPulseBlinking() const {
    return pulseBlinkTimer != nullptr;
  }

  // One full flash, then restore previous duty (usually awake dim).
  void blink() {
    pulse(1);
  }

  // Two full flashes, then restore previous duty.
  void doubleBlink() {
    pulse(2);
  }

  // Error pattern: rapid full/off flashes, then restore previous duty.
  void rapidErrorBlink() {
    pulse(10);
  }

  bool isOn() const {
    return currentDuty > DutyOff;
  }

  bool isFull() const {
    return currentDuty >= DutyFull;
  }

private:
  static constexpr uint8_t PwmChannel = 0;
  static constexpr uint32_t PwmFreqHz = 5000;
  static constexpr uint8_t PwmResolutionBits = 8;
  static constexpr uint32_t DutyOff = 0;
  static constexpr uint32_t DutyAwake = 77; // ~30%
  static constexpr uint32_t DutyFull = 255;
  static constexpr uint32_t PulseMs = 100;
  static constexpr uint32_t DefaultUploadPulseMs = 400;

  Mode mode = Mode::AlwaysAwake;
  uint32_t currentDuty = DutyOff;
  bool pwmAttached = false;
  bool blinkHigh = false;
  esp_timer_handle_t pulseBlinkTimer = nullptr;

  void ensurePwm() {
    if (pwmAttached) {
      return;
    }
    pinMode(pins::AwakeLedPin, OUTPUT);
    ledcSetup(PwmChannel, PwmFreqHz, PwmResolutionBits);
    ledcAttachPin(pins::AwakeLedPin, PwmChannel);
    pwmAttached = true;
  }

  void writeDuty(uint32_t duty) {
    ledcWrite(PwmChannel, duty);
    currentDuty = duty;
  }

  static void onPulseBlink(void *arg) {
    auto *self = static_cast<AwakeLed *>(arg);
    self->blinkHigh = !self->blinkHigh;
    self->writeDuty(self->blinkHigh ? DutyFull : DutyAwake);
  }

  void pulse(uint8_t count) {
    stopPulseBlink();
    ensurePwm();
    const uint32_t previous = currentDuty;
    for (uint8_t i = 0; i < count; ++i) {
      writeDuty(DutyFull);
      delay(PulseMs);
      writeDuty(DutyOff);
      delay(PulseMs);
    }
    writeDuty(previous);
  }
};
