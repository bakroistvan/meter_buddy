#pragma once

#include "storage.h"
#include "battery.h"

namespace upload {

enum class Result {
  Success,
  WifiFailed,
  HttpFailed,
  ServerRejected,
};

bool ensureWifiConnected();
bool syncRtcFromNetwork();
// Powers Wi-Fi off unless KeepWifiConnectedWhenAwake. Session owner calls after POSTs/OTA.
bool disconnectWifiIfAllowed();
// batteryReading may be nullptr to omit top-level battery_v / battery_pct_est.
// Each reading always includes stored battery_v / battery_pct_est from record.batteryMv.
// uploadSessionId nullptr (or empty) omits upload_session_id / last_batch (diagnostics preview).
String buildBody(const storage::UploadBatch &batch, const battery::Reading *batteryReading,
                 const char *uploadSessionId = nullptr, bool lastBatch = false);
// Keep-alive HTTP/HTTPS client for one upload wake. Constructs TLS only for https://.
// end() before OTA (different URL). Destructor calls end().
class HttpSession {
public:
  HttpSession();
  ~HttpSession();
  HttpSession(const HttpSession &) = delete;
  HttpSession &operator=(const HttpSession &) = delete;

  // uploadSessionId required for real POSTs (1–64 chars); lastBatch true iff !batch.truncated.
  Result post(const storage::UploadBatch &batch, const battery::Reading *batteryReading,
              const char *uploadSessionId, bool lastBatch);
  void end();

private:
  bool ensureBegun();
  struct Impl;
  Impl *impl_;
};
// One-shot POST (own session). Generates an ephemeral upload_session_id.
// Prefer HttpSession for a multi-batch drain.
Result sendBatch(const storage::UploadBatch &batch, const battery::Reading *batteryReading);
const char *resultName(Result result);
void checkFirmwareUpdate();

} // namespace upload
