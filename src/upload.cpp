#include "upload.h"

#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>

#include "config.h"
#include "rtc_clock.h"

namespace upload {

namespace {

String iso8601(uint32_t unixTime) {
  time_t raw = unixTime;
  tm timeinfo{};
  gmtime_r(&raw, &timeinfo);

  char out[25];
  strftime(out, sizeof(out), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(out);
}

String buildBody(const storage::UploadBatch &batch, const battery::Reading &batteryReading) {
  String body;
  body.reserve(384 + batch.count * 96);
  body += "{\"device_id\":\"";
  body += config::DeviceId;
  body += "\",\"meter_impulses_per_kwh\":";
  body += config::MeterImpulsesPerKwh;
  body += ",\"upload_trigger\":\"button\",\"battery_v\":";
  body += String(batteryReading.volts, 2);
  body += ",\"battery_pct_est\":";
  body += String(batteryReading.percent);
  body += ",\"readings\":[";

  for (uint8_t i = 0; i < batch.count; ++i) {
    const auto &record = batch.records[i];
    if (i > 0) {
      body += ',';
    }
    body += "{\"timestamp\":\"";
    body += iso8601(record.periodEnd);
    body += "\",\"period_start\":\"";
    body += iso8601(record.periodStart);
    body += "\",\"pulses\":";
    body += String(record.pulses);
    body += "}";
  }

  body += "]}";
  return body;
}

void logEvent(const char *message) {
  if (config::EnableSerialLogs) {
    Serial.println(message);
  }
}

bool disconnectWifiIfAllowed() {
  if (config::KeepWifiConnectedWhenAwake) {
    return true;
  }
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  return true;
}

} // namespace

bool ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  logEvent("wifi connect start");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(!config::KeepWifiConnectedWhenAwake);
  WiFi.begin(config::WifiSsid, config::WifiPassword);

  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < config::WifiConnectTimeoutMs) {
    delay(250);
  }

  const bool connected = WiFi.status() == WL_CONNECTED;
  logEvent(connected ? "wifi connected" : "wifi connect failed");
  return connected;
}

bool syncRtcFromNetwork() {
  logEvent("ntp sync start");
  configTime(0, 0, config::NtpServer1, config::NtpServer2);

  const uint32_t started = millis();
  time_t now = 0;
  while (millis() - started < config::NtpSyncTimeoutMs) {
    now = time(nullptr);
    if (now > 1700000000) {
      rtc_clock::adjustUnix(static_cast<uint32_t>(now));
      rtc_clock::scheduleNextWakeAlarm();
      logEvent("ntp sync success");
      return true;
    }
    delay(250);
  }
  logEvent("ntp sync failed");
  return false;
}

Result sendBatch(const storage::UploadBatch &batch, const battery::Reading &batteryReading) {
  if (!ensureWifiConnected()) {
    disconnectWifiIfAllowed();
    return Result::WifiFailed;
  }

  syncRtcFromNetwork();

  if (batch.count == 0) {
    logEvent("upload skipped: no data");
    disconnectWifiIfAllowed();
    return Result::NoData;
  }

  // Use plain TCP for http://, TLS for https://
  const bool useTls = strncmp(config::UploadUrl, "https://", 8) == 0;

  WiFiClient *client;
  WiFiClient plainClient;
  WiFiClientSecure tlsClient;

  if (useTls) {
    if (config::AllowInsecureTls) {
      tlsClient.setInsecure();
    } else if (strlen(config::TlsCaCert) > 0) {
      tlsClient.setCACert(config::TlsCaCert);
    } else {
      logEvent("upload failed: tls not configured");
      disconnectWifiIfAllowed();
      return Result::HttpFailed;
    }
    client = &tlsClient;
  } else {
    client = &plainClient;
  }

  if (config::EnableSerialLogs) {
    Serial.printf("upload url=%s\n", config::UploadUrl);
    Serial.printf("upload wifi rssi=%d\n", WiFi.RSSI());
  }

  HTTPClient http;
  http.setTimeout(config::HttpTimeoutMs);
  if (!http.begin(*client, config::UploadUrl)) {
    logEvent("upload failed: http begin");
    disconnectWifiIfAllowed();
    return Result::HttpFailed;
  }

  http.setAuthorization(config::BasicAuthUser, config::BasicAuthPassword);
  http.addHeader("Content-Type", "application/json");

  const String body = buildBody(batch, batteryReading);
  if (config::EnableSerialLogs) {
    Serial.printf("upload post start records=%u bytes=%u\n", batch.count, body.length());
  }
  const int status = http.POST(body);
  http.end();
  disconnectWifiIfAllowed();

  if (status < 0) {
    if (config::EnableSerialLogs) {
      Serial.printf("upload http error=%d reason=%s\n", status, HTTPClient::errorToString(status).c_str());
    }
    return Result::HttpFailed;
  }
  if (status == 200 || status == 201) {
    if (config::EnableSerialLogs) {
      Serial.printf("upload accepted status=%d\n", status);
    }
    return Result::Success;
  }
  if (config::EnableSerialLogs) {
    Serial.printf("upload rejected status=%d\n", status);
  }
  return Result::ServerRejected;
}

const char *resultName(Result result) {
  switch (result) {
  case Result::Success:
    return "success";
  case Result::NoData:
    return "no_data";
  case Result::WifiFailed:
    return "wifi_failed";
  case Result::HttpFailed:
    return "http_failed";
  case Result::ServerRejected:
    return "server_rejected";
  }
  return "unknown";
}

} // namespace upload
