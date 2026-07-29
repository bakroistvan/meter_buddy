#pragma once

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
Result sendBatch(const storage::UploadBatch &batch);
const char *resultName(Result result);
void checkFirmwareUpdate();

} // namespace upload
