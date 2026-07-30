#pragma once

#include <Arduino.h>
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

  // Idle-awake indicator: 50% PWM.
  void setAwake() {
    ensurePwm();
    writeDuty(DutyAwake);
  }

  void setSleep() {
    writeDuty(DutyOff);
    if (pwmAttached) {
      ledcDetachPin(pins::AwakeLedPin);
      pwmAttached = false;
    }
    pinMode(pins::AwakeLedPin, INPUT_PULLDOWN);
  }

  // Full brightness — used for upload-in-progress.
  void setOn() {
    ensurePwm();
    writeDuty(DutyFull);
  }

  void setOff() {
    ensurePwm();
    writeDuty(DutyOff);
  }

  // One full flash, then restore previous duty (usually 50% awake).
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
  static constexpr uint32_t DutyAwake = 77; // 30%
  static constexpr uint32_t DutyFull = 255;
  static constexpr uint32_t PulseMs = 100;

  Mode mode = Mode::AlwaysAwake;
  uint32_t currentDuty = DutyOff;
  bool pwmAttached = false;

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

  void pulse(uint8_t count) {
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
