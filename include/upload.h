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
String buildBody(const storage::UploadBatch &batch, const battery::Reading *batteryReading);
// POST only; caller owns Wi-Fi connect/NTP/disconnect for the upload session.
Result sendBatch(const storage::UploadBatch &batch, const battery::Reading *batteryReading);
const char *resultName(Result result);
void checkFirmwareUpdate();

} // namespace upload
