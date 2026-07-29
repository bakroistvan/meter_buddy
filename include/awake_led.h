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
    pinMode(pins::AwakeLedPin, OUTPUT);
    digitalWrite(pins::AwakeLedPin, LOW);
  }

  void setMode(Mode newMode) {
    mode = newMode;
  }

  void setAwake() {
    if (mode == Mode::WakeFromDeepSleep) {
      digitalWrite(pins::AwakeLedPin, HIGH);
    }
  }

  void setSleep() {
    digitalWrite(pins::AwakeLedPin, LOW);
  }

  void setOn() {
    digitalWrite(pins::AwakeLedPin, HIGH);
  }

  void setOff() {
    digitalWrite(pins::AwakeLedPin, LOW);
  }

  void blink() {
    if (mode == Mode::WakeFromDeepSleep) {
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
      delay(100);
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
    } else {
      digitalWrite(pins::AwakeLedPin, HIGH);
      delay(100);
      digitalWrite(pins::AwakeLedPin, LOW);
    }
  }

  void doubleBlink() {
    if (mode == Mode::WakeFromDeepSleep) {
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
      delay(100);
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
      delay(100);
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
      delay(100);
      digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
    } else {
      digitalWrite(pins::AwakeLedPin, HIGH);
      delay(100);
      digitalWrite(pins::AwakeLedPin, LOW);
      delay(100);
      digitalWrite(pins::AwakeLedPin, HIGH);
      delay(100);
      digitalWrite(pins::AwakeLedPin, LOW);
    }
  }

  void rapidErrorBlink() {
    if (mode == Mode::WakeFromDeepSleep) {
      for (uint8_t i = 0; i < 10; ++i) {
        digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
        delay(100);
        digitalWrite(pins::AwakeLedPin, !digitalRead(pins::AwakeLedPin));
        delay(100);
      }
    } else {
      for (uint8_t i = 0; i < 10; ++i) {
        digitalWrite(pins::AwakeLedPin, HIGH);
        delay(100);
        digitalWrite(pins::AwakeLedPin, LOW);
        delay(100);
      }
    }
  }

  bool isOn() const {
    return digitalRead(pins::AwakeLedPin) == HIGH;
  }

private:
  Mode mode = Mode::AlwaysAwake;
};
