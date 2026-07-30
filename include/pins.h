#pragma once

#include <Arduino.h>

namespace pins {

constexpr uint8_t BatteryAdcPin = A0; // D0 / A0

// D1 (GPIO3) is the user upload button and can wake the ESP32-C3 from deep sleep.
constexpr uint8_t UploadButtonPin = D1;

// D2 (GPIO4) is the pulse input from TEMT6000. The TEMT6000 must be powered from 3.3V directly
// so it can wake the ESP32-C3 from deep sleep when a pulse arrives.
constexpr uint8_t PulseWakePin = D2;

// D3 (GPIO5) is the RTC wake pin.
constexpr uint8_t RtcWakePin = D3;

constexpr uint8_t I2cSdaPin = D4;
constexpr uint8_t I2cSclPin = D5;

constexpr uint8_t PulseLedPin = D8; // Dedicated pulse indicator LED
constexpr uint8_t AwakeLedPin = D10; // GPIO10, debug/status LED

} // namespace pins
