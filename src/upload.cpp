#include "upload.h"

#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <cstdio>
#include <esp_system.h>
#include <time.h>

#include "config.h"
#include "battery.h"
#include "rtc_clock.h"

namespace upload {

namespace {

void appendIso8601(String &out, uint32_t unixTime) {
  time_t raw = unixTime;
  tm timeinfo{};
  gmtime_r(&raw, &timeinfo);

  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  out += buf;
}

void appendFixed3(String &out, float value) {
  char buf[16];
  snprintf(buf, sizeof(buf), "%.3f", static_cast<double>(value));
  out += buf;
}

const char *errorMessage(const char *code) {
  if (strcmp(code, "no_data") == 0) {
    return "no unsynced readings";
  }
  if (strcmp(code, "crc_mismatch") == 0) {
    return "record CRC failed";
  }
  if (strcmp(code, "storage_unavailable") == 0) {
    return "storage not ready";
  }
  if (strcmp(code, "batch_truncated") == 0) {
    return "upload batch truncated";
  }
  if (strcmp(code, "low_battery") == 0) {
    return "protection lock from low battery";
  }
  if (strcmp(code, "brownout_lock") == 0) {
    return "protection lock from brown-out reset";
  }
  return code != nullptr ? code : "unknown";
}

void appendJsonEscaped(String &out, const char *text) {
  if (text == nullptr) {
    return;
  }
  for (const char *p = text; *p != '\0'; ++p) {
    const char c = *p;
    if (c == '"' || c == '\\') {
      out += '\\';
    }
    out += c;
  }
}

void logEvent(const char *message) {
  if (config::EnableSerialLogs) {
    Serial.println(message);
  }
}

// 16 random bytes → 32 hex chars + NUL. Same helper used by sendBatch ephemeral sessions.
void fillEphemeralUploadSessionId(char out[33]) {
  static const char kHex[] = "0123456789abcdef";
  for (int i = 0; i < 16; ++i) {
    const uint8_t b = static_cast<uint8_t>(esp_random() & 0xffu);
    out[i * 2] = kHex[(b >> 4) & 0x0f];
    out[i * 2 + 1] = kHex[b & 0x0f];
  }
  out[32] = '\0';
}

void drainHttpResponse(HTTPClient &http) {
  WiFiClient *stream = http.getStreamPtr();
  if (stream == nullptr) {
    return;
  }
  int remaining = http.getSize();
  const uint32_t started = millis();
  while (http.connected() && (millis() - started) < 2000) {
    while (stream->available() > 0) {
      stream->read();
      if (remaining > 0) {
        --remaining;
      }
    }
    if (remaining <= 0 && !stream->available()) {
      break;
    }
    delay(1);
  }
}

} // namespace

struct HttpSession::Impl {
  WiFiClient *plain = nullptr;
  WiFiClientSecure *tls = nullptr;
  WiFiClient *client = nullptr;
  HTTPClient http;
  bool begun = false;
};

HttpSession::HttpSession() : impl_(new Impl()) {}

HttpSession::~HttpSession() {
  end();
  delete impl_;
  impl_ = nullptr;
}

void HttpSession::end() {
  if (impl_ == nullptr) {
    return;
  }
  impl_->http.setReuse(false);
  if (impl_->begun) {
    impl_->http.end();
    impl_->begun = false;
  }
  delete impl_->tls;
  impl_->tls = nullptr;
  delete impl_->plain;
  impl_->plain = nullptr;
  impl_->client = nullptr;
}

bool HttpSession::ensureBegun() {
  if (impl_ == nullptr) {
    impl_ = new Impl();
  }
  if (impl_->begun && impl_->client != nullptr && impl_->client->connected()) {
    return true;
  }

  end();

  const bool useTls = strncmp(config::UploadUrl, "https://", 8) == 0;
  if (useTls) {
    impl_->tls = new WiFiClientSecure();
    if (impl_->tls == nullptr) {
      return false;
    }
    if (config::AllowInsecureTls) {
      impl_->tls->setInsecure();
    } else if (strlen(config::TlsCaCert) > 0) {
      impl_->tls->setCACert(config::TlsCaCert);
    } else {
      logEvent("upload failed: tls not configured");
      delete impl_->tls;
      impl_->tls = nullptr;
      return false;
    }
    impl_->client = impl_->tls;
  } else {
    impl_->plain = new WiFiClient();
    if (impl_->plain == nullptr) {
      return false;
    }
    impl_->client = impl_->plain;
  }

  impl_->http.setTimeout(config::HttpTimeoutMs);
  impl_->http.setReuse(true);
  if (!impl_->http.begin(*impl_->client, config::UploadUrl)) {
    logEvent("upload failed: http begin");
    end();
    return false;
  }
  if (config::EnableSerialLogs) {
    Serial.printf("upload url=%s\n", config::UploadUrl);
  }
  impl_->begun = true;
  return true;
}

Result HttpSession::post(const storage::UploadBatch &batch, const battery::Reading *batteryReading,
                         const char *uploadSessionId, bool lastBatch) {
  if (uploadSessionId == nullptr || uploadSessionId[0] == '\0') {
    logEvent("upload failed: missing upload_session_id");
    return Result::HttpFailed;
  }
  if (!ensureWifiConnected()) {
    return Result::WifiFailed;
  }
  if (!ensureBegun()) {
    return Result::HttpFailed;
  }

  if (config::EnableSerialLogs) {
    Serial.printf("upload wifi rssi=%d\n", WiFi.RSSI());
  }

  impl_->http.setAuthorization(config::BasicAuthUser, config::BasicAuthPassword);
  impl_->http.addHeader("Content-Type", "application/json");

  const String body = buildBody(batch, batteryReading, uploadSessionId, lastBatch);
  if (config::EnableSerialLogs) {
    Serial.printf("upload post start records=%u errors=%u bytes=%u session=%s last_batch=%d\n",
                  batch.count, batch.errorCount, body.length(), uploadSessionId,
                  lastBatch ? 1 : 0);
  }

  int status = impl_->http.POST(body);
  if (status < 0) {
    end();
    if (!ensureWifiConnected()) {
      return Result::WifiFailed;
    }
    if (!ensureBegun()) {
      return Result::HttpFailed;
    }
    impl_->http.setAuthorization(config::BasicAuthUser, config::BasicAuthPassword);
    impl_->http.addHeader("Content-Type", "application/json");
    status = impl_->http.POST(body);
  }

  if (status < 0) {
    if (config::EnableSerialLogs) {
      Serial.printf("upload http error=%d reason=%s\n", status, HTTPClient::errorToString(status).c_str());
    }
    end();
    return Result::HttpFailed;
  }

  drainHttpResponse(impl_->http);

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

bool disconnectWifiIfAllowed() {
  if (config::KeepWifiConnectedWhenAwake) {
    return true;
  }
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  return true;
}

String buildBody(const storage::UploadBatch &batch, const battery::Reading *batteryReading,
                 const char *uploadSessionId, bool lastBatch) {
  String body;
  body.reserve(512 + static_cast<unsigned>(batch.count) * 140 + batch.errorCount * 80);
  body += "{\"device_id\":\"";
  body += config::DeviceId;
  body += "\",\"meter_impulses_per_kwh\":";
  body += config::MeterImpulsesPerKwh;
  body += ",\"upload_trigger\":\"button\"";
  if (uploadSessionId != nullptr && uploadSessionId[0] != '\0') {
    body += ",\"upload_session_id\":\"";
    appendJsonEscaped(body, uploadSessionId);
    body += "\",\"last_batch\":";
    body += lastBatch ? "true" : "false";
  }
  if (batteryReading != nullptr) {
    body += ",\"battery_v\":";
    appendFixed3(body, batteryReading->volts);
    body += ",\"battery_pct_est\":";
    body += static_cast<unsigned>(batteryReading->percent);
  }
  body += ",\"readings\":[";

  for (uint8_t i = 0; i < batch.count; ++i) {
    const auto &record = batch.records[i];
    if (i > 0) {
      body += ',';
    }
    const uint32_t periodEnd = record.periodStart + config::RtcWakeIntervalSeconds;
    const float volts = record.batteryMv / 1000.0f;
    body += "{\"timestamp\":\"";
    appendIso8601(body, periodEnd);
    body += "\",\"period_start\":\"";
    appendIso8601(body, record.periodStart);
    body += "\",\"pulses\":";
    body += record.pulses;
    body += ",\"battery_v\":";
    appendFixed3(body, volts);
    body += ",\"battery_pct_est\":";
    body += static_cast<unsigned>(battery::estimatePercent(volts));
    body += "}";
  }

  body += "],\"errors\":[";
  for (uint8_t i = 0; i < batch.errorCount; ++i) {
    const auto &err = batch.errors[i];
    if (i > 0) {
      body += ',';
    }
    body += "{\"code\":\"";
    appendJsonEscaped(body, err.code);
    body += "\",\"message\":\"";
    appendJsonEscaped(body, errorMessage(err.code));
    body += "\"";
    if (err.detail[0] != '\0') {
      body += ",\"detail\":\"";
      appendJsonEscaped(body, err.detail);
      body += "\"";
    }
    body += "}";
  }
  body += "]}";
  return body;
}

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

Result sendBatch(const storage::UploadBatch &batch, const battery::Reading *batteryReading) {
  char uploadSessionId[33];
  fillEphemeralUploadSessionId(uploadSessionId);
  HttpSession session;
  return session.post(batch, batteryReading, uploadSessionId, !batch.truncated);
}

const char *resultName(Result result) {
  switch (result) {
  case Result::Success:
    return "success";
  case Result::WifiFailed:
    return "wifi_failed";
  case Result::HttpFailed:
    return "http_failed";
  case Result::ServerRejected:
    return "server_rejected";
  }
  return "unknown";
}

void checkFirmwareUpdate() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  
  logEvent("ota check start");

  const bool useTls = strncmp(config::FirmwareVersionUrl, "https://", 8) == 0;
  WiFiClient *client;
  WiFiClient plainClient;
  WiFiClientSecure tlsClient;

  if (useTls) {
    if (config::AllowInsecureTls) {
      tlsClient.setInsecure();
    } else if (strlen(config::TlsCaCert) > 0) {
      tlsClient.setCACert(config::TlsCaCert);
    } else {
      logEvent("ota check failed: tls not configured");
      return;
    }
    client = &tlsClient;
  } else {
    client = &plainClient;
  }

#if defined(FIRMWARE_VERSION)
  const char *currentVersion = FIRMWARE_VERSION;
#else
  const char *currentVersion = config::FirmwareVersion;
#endif

  // Arduino-ESP32 2.x: timeout via HTTPUpdate ctor; Basic Auth via request callback
  // (setAuthorization/setTimeout on HTTPUpdate arrived in core 3.x).
  HTTPUpdate updater(static_cast<int>(config::OtaTimeoutMs));
  t_httpUpdate_return ret = updater.update(
      *client, config::FirmwareVersionUrl, currentVersion, [](HTTPClient *http) {
        http->setAuthorization(config::BasicAuthUser, config::BasicAuthPassword);
      });

  if (config::EnableSerialLogs) {
    switch (ret) {
      case HTTP_UPDATE_FAILED:
        Serial.printf("ota failed Error (%d): %s\n", updater.getLastError(), updater.getLastErrorString().c_str());
        break;
      case HTTP_UPDATE_NO_UPDATES:
        Serial.println("ota no updates");
        break;
      case HTTP_UPDATE_OK:
        Serial.println("ota success");
        break;
    }
  }
}

} // namespace upload
