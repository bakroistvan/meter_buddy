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
Result sendBatch(const storage::UploadBatch &batch, const battery::Reading &battery);
const char *resultName(Result result);
void checkFirmwareUpdate();

} // namespace upload
