#pragma once

#include "certs/isrg_roots.h"

namespace config {

// Unique id sent in every upload JSON payload.
constexpr const char *DeviceId = "meter-buddy-001";
// Meter S0 constant (pulses per kWh). Included in upload JSON; must match the meter.
constexpr uint16_t MeterImpulsesPerKwh = 1000;

// Wi-Fi STA SSID used for upload, NTP, and optional OTA.
constexpr const char *WifiSsid = "Your iPhone Hotspot";
// Wi-Fi STA password.
constexpr const char *WifiPassword = "change-me";

// HTTPS POST endpoint for reading batches (must match backend /api/meter-buddy/upload).
constexpr const char *UploadUrl = "https://example.com/api/meter-buddy/upload";
// Max readings in one upload JSON. Further unsynced records go in follow-up POSTs (truncated).
constexpr uint8_t MaxUploadRecords = 128;
// Max errors[] entries on one upload JSON (no_data, crc_mismatch, batch_truncated, …).
constexpr uint8_t MaxUploadErrors = 8;
// HTTPS URL used by HTTP OTA after a successful upload session.
constexpr const char *FirmwareVersionUrl = "https://example.com/api/meter-buddy/firmware/version";
// Current firmware version string sent to the OTA endpoint (skip update if already this).
constexpr const char *FirmwareVersion = "1.0.0";
// HTTP Basic Auth username for upload and OTA. Must match backend METER_BUDDY_AUTH_USER.
constexpr const char *BasicAuthUser = "meter-buddy";
// HTTP Basic Auth password. Must match backend METER_BUDDY_AUTH_PASSWORD.
constexpr const char *BasicAuthPassword = "change-me";

// Default: vendored Let's Encrypt ISRG Root X1 + X2 (see certs/isrg_roots.h).
// Override only if pinning a different CA. Do not paste rotating leaf certs here.
constexpr const char *TlsCaCert = IsrgRootCerts;

// Skip TLS cert verification. Dev only; leave false for production HTTPS.
constexpr bool AllowInsecureTls = false;
// Max wait for Wi-Fi association before upload/NTP/OTA is aborted.
constexpr uint32_t WifiConnectTimeoutMs = 30000;
// HTTP client timeout for each upload POST.
constexpr uint32_t HttpTimeoutMs = 20000;

// Primary NTP host after Wi-Fi connects (sets system time and DS3231).
constexpr const char *NtpServer1 = "pool.ntp.org";
// Fallback NTP host.
constexpr const char *NtpServer2 = "time.google.com";
// Max wait for a valid NTP time after configTime().
constexpr uint32_t NtpSyncTimeoutMs = 10000;

// Isolated vs burst pulse wakes:
//
//   isolated (gap > PulseAwakeThresholdMs):
//     [sleep]------*------[sleep]          store 1, sleep immediately
//                  ^pulse
//
//   burst (gap <= PulseAwakeThresholdMs):
//     [sleep]--*-*-*-~~~~~~~~~~~~~~~~[sleep]
//              |<=8s|  |<-- 30s quiet -->|
//              stay awake, ISR-count until PulseAwakeQuietMs with no pulses
constexpr uint32_t PulseAwakeThresholdMs = 8000; // Gap vs last pulse: ≤ this → burst counting (ms)
constexpr uint32_t PulseAwakeQuietMs = 30000; // No pulses for this long → leave burst mode and sleep (ms)
constexpr uint32_t PulseDebounceMs = 50; // Ignore pulse/button edges closer than this (ms)
constexpr uint32_t AwakePulseFlushMs = 5000; // While awake, flush ISR pulse counts to storage this often (ms)
constexpr uint32_t WifiReconnectIntervalMs = 10000; // When keeping Wi-Fi up, poll/reconnect this often (ms)
constexpr uint32_t UploadLongPressMs = 4000; // Hold upload button this long to toggle StayAwakeBoot (ms)

// DS3231 alarm period. Also the stored reading period length (seconds). Default 60.
constexpr uint16_t RtcWakeIntervalSeconds = 60;

// Pause after forcing Wi-Fi off before ADC sample used for RTC roll / upload.
constexpr uint32_t BatteryAdcSettleMs = 80;

// Pack voltage thresholds for button-only protection sleep (hysteresis).
// Resting pack V below this (and USB unplugged) latches protection; pulse/RTC wakes disarmed.
constexpr float BatteryRadioBlockVolts = 3.30f;
// Clear protection only when resting sample is ≥ this (or USB powered).
constexpr float BatteryRadioUnlockVolts = 3.50f;

// Enter deep sleep after pulse/RTC/upload cycles. false = stay in loop() (bench).
constexpr bool EnableDeepSleep = true;
// Keep STA connected after POST and when entering stay-awake / diagnostics.
constexpr bool KeepWifiConnectedWhenAwake = false;
// Compile-time default for stay-awake before /stay_awake.dat exists; long-press toggles the file.
constexpr bool StayAwakeBoot = false;
// Print debug lines on Serial when USB-serial is up.
constexpr bool EnableSerialLogs = true;

// LED event mask: see include/led_events.h (included from config.h).
// Override with #define METER_BUDDY_LED_EVENT_MASK in local_config.h (0 = bench, all on).

} // namespace config
