#pragma once

#include "battery.h"
#include "storage.h"

namespace upload {

enum class Result {
  Success,
  NoData,
  WifiFailed,
  HttpFailed,
  ServerRejected,
};

bool ensureWifiConnected();
bool syncRtcFromNetwork();
Result sendBatch(const storage::UploadBatch &batch, const battery::Reading &batteryReading);
const char *resultName(Result result);

} // namespace upload
