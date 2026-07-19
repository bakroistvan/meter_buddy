#pragma once

#include <Arduino.h>

namespace pins {

constexpr gpio_num_t BatteryAdcWakePin = GPIO_NUM_2; // D0 / A0
constexpr uint8_t BatteryAdcPin = A0;

// D1 (GPIO3) is the user upload button.
// The TEMT6000 must be powered from 3.3V directly so it can
// wake the ESP32-C3 from deep sleep when a pulse arrives.
constexpr gpio_num_t PulseWakePin = GPIO_NUM_4; // D2
constexpr gpio_num_t RtcWakePin = GPIO_NUM_5;   // D3

constexpr uint8_t I2cSdaPin = D4;
constexpr uint8_t I2cSclPin = D5;

constexpr gpio_num_t UploadButtonWakePin = GPIO_NUM_3; // (unused in wake mask)
constexpr uint8_t UploadButtonPin = D1;

constexpr uint8_t AwakeLedPin = D10; // GPIO10, debug LED: on when awake, off when sleeping

} // namespace pins
