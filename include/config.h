#pragma once

#include <Arduino.h>

#if __has_include("local_config.h")
#include "local_config.h"
#else
#include "config.example.h"
#endif

#include "led_events.h"
