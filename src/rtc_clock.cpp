#include "config.h"
#include "rtc_clock.h"

namespace rtc_clock {

namespace {
RTC_DS3231 rtc;
}

bool begin() {
  if (!rtc.begin()) {
    return false;
  }

  rtc.disable32K();
  clearAlarm();
  rtc.writeSqwPinMode(DS3231_OFF);
  return true;
}

uint32_t nowUnix() {
  return rtc.now().unixtime();
}

bool adjustUnix(uint32_t timestamp) {
  rtc.adjust(DateTime(timestamp));
  return true;
}

bool clearAlarm() {
  rtc.clearAlarm(1);
  rtc.clearAlarm(2);
  return true;
}

bool scheduleNextWakeAlarm() {
  const DateTime now = rtc.now();
  constexpr uint32_t intervalSec = config::RtcWakeIntervalSeconds;

  DateTime next(now.unixtime() + intervalSec);
  rtc.disableAlarm(1);
  rtc.disableAlarm(2);
  
  // Match hours, minutes, and seconds. Safe for intervals < 24 hours.
  return rtc.setAlarm1(next, DS3231_A1_Hour);
}

} // namespace rtc_clock
