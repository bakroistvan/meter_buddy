#pragma once

#include <Arduino.h>

namespace pins {

constexpr gpio_num_t BatteryAdcWakePin = GPIO_NUM_2; // D0 / A0
constexpr uint8_t BatteryAdcPin = A0;

// D1 is intentionally unused. The TEMT6000 must be powered from 3.3V so it can
// wake the ESP32-C3 from deep sleep when a pulse arrives.
constexpr gpio_num_t PulseWakePin = GPIO_NUM_4; // D2
constexpr gpio_num_t RtcWakePin = GPIO_NUM_5;   // D3

constexpr uint8_t I2cSdaPin = D4;
constexpr uint8_t I2cSclPin = D5;

constexpr gpio_num_t UploadButtonWakePin = GPIO_NUM_21; // D6 on XIAO ESP32-C3
constexpr uint8_t UploadButtonPin = D6;

} // namespace pins
