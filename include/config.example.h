#pragma once

#include "certs/isrg_roots.h"

namespace config {

constexpr const char *DeviceId = "meter-buddy-001";
constexpr uint16_t MeterImpulsesPerKwh = 1000;

constexpr const char *WifiSsid = "Your iPhone Hotspot";
constexpr const char *WifiPassword = "change-me";

constexpr const char *UploadUrl = "https://example.com/api/meter-buddy/upload";
constexpr const char *FirmwareVersionUrl = "https://example.com/api/meter-buddy/firmware/version";
constexpr const char *FirmwareVersion = "1.0.0";
constexpr const char *BasicAuthUser = "meter-buddy";
constexpr const char *BasicAuthPassword = "change-me";

// Default: vendored Let's Encrypt ISRG Root X1 + X2 (see certs/isrg_roots.h).
// Override only if pinning a different CA. Do not paste rotating leaf certs here.
constexpr const char *TlsCaCert = IsrgRootCerts;

constexpr bool AllowInsecureTls = false;
constexpr uint32_t WifiConnectTimeoutMs = 30000;
constexpr uint32_t HttpTimeoutMs = 20000;

constexpr const char *NtpServer1 = "pool.ntp.org";
constexpr const char *NtpServer2 = "time.google.com";
constexpr uint32_t NtpSyncTimeoutMs = 10000;

// If the previous pulse was this recent, avoid immediate deep sleep and count
// pulses while awake until the meter is quiet again.
constexpr uint32_t PulseAwakeThresholdMs = 8000; // Time between pulses to trigger awake counting (ms)
constexpr uint32_t PulseAwakeQuietMs = 30000; // Time with no pulses before returning to sleep (ms)
constexpr uint32_t PulseDebounceMs = 50; // Debounce time for pulse detection (ms)
constexpr uint32_t AwakePulseFlushMs = 5000; // Interval for flushing counted pulses to storage while awake (ms)
constexpr uint32_t WifiReconnectIntervalMs = 10000; // Interval for checking and reconnecting WiFi (ms)
constexpr uint32_t UploadLongPressMs = 4000; // Hold upload button this long to toggle StayAwakeBoot

// RTC wake interval in seconds. Default 60.
constexpr uint16_t RtcWakeIntervalSeconds = 60;

// Pause after forcing Wi-Fi off before ADC sample used for RTC roll / upload.
constexpr uint32_t BatteryAdcSettleMs = 80;

// Pack voltage thresholds for button-only protection sleep (hysteresis).
// Below block → latch lock; clear only at/above unlock (or USB powered).
constexpr float BatteryRadioBlockVolts = 3.30f;
constexpr float BatteryRadioUnlockVolts = 3.50f;

constexpr bool EnableDeepSleep = true;
constexpr bool KeepWifiConnectedWhenAwake = false;
constexpr bool StayAwakeBoot = false;
constexpr bool EnableSerialLogs = true;

} // namespace config
