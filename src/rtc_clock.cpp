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

bool scheduleNextDailyAlarm() {
  const DateTime now = rtc.now();
  DateTime next(now.year(), now.month(), now.day(), 0, 0, 0);
  if (next.unixtime() <= now.unixtime()) {
    next = next + TimeSpan(1, 0, 0, 0);
  }

  rtc.disableAlarm(1);
  rtc.disableAlarm(2);
  return rtc.setAlarm1(next, DS3231_A1_Hour);
}

} // namespace rtc_clock
