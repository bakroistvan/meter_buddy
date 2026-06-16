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

bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(true);
  WiFi.begin(config::WifiSsid, config::WifiPassword);

  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < config::WifiConnectTimeoutMs) {
    delay(250);
  }
  return WiFi.status() == WL_CONNECTED;
}

bool syncRtcFromNetwork() {
  configTime(0, 0, config::NtpServer1, config::NtpServer2);

  const uint32_t started = millis();
  time_t now = 0;
  while (millis() - started < config::NtpSyncTimeoutMs) {
    now = time(nullptr);
    if (now > 1700000000) {
      rtc_clock::adjustUnix(static_cast<uint32_t>(now));
      rtc_clock::scheduleNextDailyAlarm();
      return true;
    }
    delay(250);
  }
  return false;
}

} // namespace

Result sendBatch(const storage::UploadBatch &batch, const battery::Reading &batteryReading) {
  if (!connectWifi()) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return Result::WifiFailed;
  }

  syncRtcFromNetwork();

  if (batch.count == 0) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return Result::NoData;
  }

  WiFiClientSecure client;
  if (config::AllowInsecureTls) {
    client.setInsecure();
  } else if (strlen(config::TlsCaCert) > 0) {
    client.setCACert(config::TlsCaCert);
  } else {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return Result::HttpFailed;
  }

  HTTPClient http;
  http.setTimeout(config::HttpTimeoutMs);
  if (!http.begin(client, config::UploadUrl)) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return Result::HttpFailed;
  }

  http.setAuthorization(config::BasicAuthUser, config::BasicAuthPassword);
  http.addHeader("Content-Type", "application/json");

  const String body = buildBody(batch, batteryReading);
  const int status = http.POST(body);
  http.end();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);

  if (status < 0) {
    return Result::HttpFailed;
  }
  if (status == 200 || status == 201) {
    return Result::Success;
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
