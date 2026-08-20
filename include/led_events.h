#pragma once

#include <cstdint>

// Override before including config.h (e.g. in local_config.h):
//   #define METER_BUDDY_LED_EVENT_MASK 0
// 0 = show all routine indicators (bench). Default masks Awake|RtcRoll|Pulse.

#ifndef METER_BUDDY_LED_EVENT_MASK
#define METER_BUDDY_LED_EVENT_MASK                                               \
  (config::led_event::Awake | config::led_event::RtcRoll | config::led_event::Pulse)
#endif

namespace config {

namespace led_event {
constexpr uint8_t Awake = 1 << 0; // dim PWM idle-awake (status LED)
constexpr uint8_t RtcRoll = 1 << 1; // status blink on period roll
constexpr uint8_t Pulse = 1 << 2; // D8 ~100 ms per accepted pulse
} // namespace led_event

constexpr uint8_t LedEventMask = METER_BUDDY_LED_EVENT_MASK;

constexpr bool ledEventEnabled(uint8_t bit) {
  return (LedEventMask & bit) == 0;
}

} // namespace config
