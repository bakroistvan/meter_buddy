#include "config.h"
#include "rtc_clock.h"

namespace rtc_clock {

namespace {
RTC_DS3231 rtc;
bool initialized = false;
}

bool beginTimeOnly() {
  if (!rtc.begin()) {
    initialized = false;
    return false;
  }

  initialized = true;
  return true;
}

bool begin() {
  if (!beginTimeOnly()) {
    return false;
  }

  rtc.disable32K();
  rtc.writeSqwPinMode(DS3231_OFF);
  clearAlarm();
  return true;
}

uint32_t nowUnix() {
  if (!initialized) {
    return 0;
  }
  return rtc.now().unixtime();
}

bool adjustUnix(uint32_t timestamp) {
  if (!initialized) {
    return false;
  }
  rtc.adjust(DateTime(timestamp));
  return true;
}

bool clearAlarm() {
  if (!initialized) {
    return false;
  }
  rtc.clearAlarm(1);
  rtc.clearAlarm(2);
  return true;
}

bool disableWakeAlarm() {
  if (!initialized) {
    return false;
  }
  rtc.clearAlarm(1);
  rtc.clearAlarm(2);
  rtc.disableAlarm(1);
  rtc.disableAlarm(2);
  return true;
}

bool scheduleNextWakeAlarm() {
  if (!initialized) {
    return false;
  }
  const DateTime now = rtc.now();
  constexpr uint32_t intervalSec = config::RtcWakeIntervalSeconds;

  DateTime next(now.unixtime() + intervalSec);
  rtc.disableAlarm(1);
  rtc.disableAlarm(2);

  // Match hours, minutes, and seconds. Safe for intervals < 24 hours.
  return rtc.setAlarm1(next, DS3231_A1_Hour);
}

uint32_t getNextAlarmUnix() {
  if (!initialized) {
    return 0;
  }

  // Read the programmed Alarm 1 registers. Alarm 1 is configured in
  // scheduleNextWakeAlarm() as a daily hour/minute/second alarm, so the
  // date stored by getAlarm1() is only a placeholder from the DS3231.
  const DateTime now = rtc.now();
  const DateTime alarm = rtc.getAlarm1();
  DateTime next(now.year(), now.month(), now.day(),
                alarm.hour(), alarm.minute(), alarm.second());

  if (next.unixtime() <= now.unixtime()) {
    next = DateTime(next.unixtime() + 24UL * 60UL * 60UL);
  }
  return next.unixtime();
}

} // namespace rtc_clock

