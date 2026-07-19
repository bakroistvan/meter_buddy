#pragma once

#include <Arduino.h>
#include <RTClib.h>

namespace rtc_clock {

bool begin();
bool beginTimeOnly();
uint32_t nowUnix();
bool adjustUnix(uint32_t timestamp);
bool clearAlarm();
bool scheduleNextWakeAlarm();

} // namespace rtc_clock
