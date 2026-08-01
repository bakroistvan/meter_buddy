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
// batteryReading may be nullptr to omit top-level battery_v / battery_pct_est.
String buildBody(const storage::UploadBatch &batch, const battery::Reading *batteryReading);
Result sendBatch(const storage::UploadBatch &batch, const battery::Reading *batteryReading);
const char *resultName(Result result);
void checkFirmwareUpdate();

} // namespace upload
