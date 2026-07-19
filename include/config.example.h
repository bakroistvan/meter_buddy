#pragma once

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

// Replace with your server CA certificate or pinned certificate in PEM format.
// Keep empty only for local development if AllowInsecureTls is true.
constexpr const char *TlsCaCert = R"EOF(
)EOF";

constexpr bool AllowInsecureTls = false;
constexpr uint32_t WifiConnectTimeoutMs = 30000;
constexpr uint32_t HttpTimeoutMs = 20000;

constexpr const char *NtpServer1 = "pool.ntp.org";
constexpr const char *NtpServer2 = "time.google.com";
constexpr uint32_t NtpSyncTimeoutMs = 10000;

// If the previous pulse was this recent, avoid immediate deep sleep and count
// pulses while awake until the meter is quiet again.
constexpr uint32_t PulseAwakeThresholdMs = 8000;
constexpr uint32_t PulseAwakeQuietMs = 30000;
constexpr uint32_t PulseAwakeMaxMs = 300000;
constexpr uint32_t PulseDebounceMs = 50;
constexpr uint32_t AwakePulseFlushMs = 5000;
constexpr uint32_t WifiReconnectIntervalMs = 10000;

// RTC wake interval in seconds. Default 60.
constexpr uint16_t RtcWakeIntervalSeconds = 60;

constexpr bool EnableDeepSleep = true;
constexpr bool KeepWifiConnectedWhenAwake = false;
constexpr bool StayAwakeOnUsbBoot = true;
constexpr bool EnableSerialLogs = true;

} // namespace config
