#pragma once

#include <Arduino.h>

namespace battery {

struct Reading {
  float volts;
  uint8_t percent;
};

void begin();
Reading sample();
uint8_t estimatePercent(float volts);

} // namespace battery

