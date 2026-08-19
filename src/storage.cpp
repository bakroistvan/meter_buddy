#include "storage.h"

#include <cstdio>
#include <LittleFS.h>
#include <FS.h>

#include "config.h"

namespace storage {

namespace {

bool initialized = false;

RTC_DATA_ATTR uint32_t rtcCurrentPeriodStart = 0;
RTC_DATA_ATTR uint16_t rtcCurrentPulses = 0;

uint32_t nextSequence = 1;
uint32_t syncedThrough = 0;
bool stayAwakeBootCached = config::StayAwakeBoot;
bool protectionLockedCached = false;
bool pendingBrownoutError = false;
bool pendingLowBatteryError = false;

const char *RecordsFile = "/records.bin";
const char *SyncFile = "/sync.dat";
const char *StayAwakeFile = "/stay_awake.dat";
const char *ProtectionFile = "/brownout.dat";

struct __attribute__((packed)) ProtectionFileState {
  uint8_t locked;
  uint8_t pendingBrownout;
  uint8_t pendingLowBattery;
};

uint16_t crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : crc >> 1;
    }
  }
  return crc;
}

template <typename T> uint16_t objectCrc(const T &value) {
  return crc16(reinterpret_cast<const uint8_t *>(&value), sizeof(T) - sizeof(uint16_t));
}

bool loadSyncState() {
  File file = LittleFS.open(SyncFile, FILE_READ);
  if (!file) {
    syncedThrough = 0;
    return false;
  }
  if (file.size() == sizeof(syncedThrough)) {
    file.read(reinterpret_cast<uint8_t*>(&syncedThrough), sizeof(syncedThrough));
  }
  file.close();
  return true;
}

bool saveSyncState() {
  File file = LittleFS.open(SyncFile, FILE_WRITE);
  if (!file) return false;
  file.write(reinterpret_cast<const uint8_t*>(&syncedThrough), sizeof(syncedThrough));
  file.close();
  return true;
}

void loadStayAwakeState() {
  stayAwakeBootCached = config::StayAwakeBoot;
  File file = LittleFS.open(StayAwakeFile, FILE_READ);
  if (!file) {
    return;
  }
  if (file.size() >= 1) {
    uint8_t value = 0;
    if (file.read(&value, 1) == 1) {
      stayAwakeBootCached = value != 0;
    }
  }
  file.close();
}

bool saveStayAwakeState() {
  File file = LittleFS.open(StayAwakeFile, FILE_WRITE);
  if (!file) {
    return false;
  }
  const uint8_t value = stayAwakeBootCached ? 1 : 0;
  const bool ok = file.write(&value, 1) == 1;
  file.close();
  return ok;
}

void loadProtectionState() {
  protectionLockedCached = false;
  pendingBrownoutError = false;
  pendingLowBatteryError = false;
  File file = LittleFS.open(ProtectionFile, FILE_READ);
  if (!file) {
    return;
  }
  ProtectionFileState state{};
  if (file.read(reinterpret_cast<uint8_t *>(&state), sizeof(state)) == sizeof(state)) {
    protectionLockedCached = state.locked != 0;
    pendingBrownoutError = state.pendingBrownout != 0;
    pendingLowBatteryError = state.pendingLowBattery != 0;
  }
  file.close();
}

bool saveProtectionState() {
  if (!initialized) {
    return false;
  }
  File file = LittleFS.open(ProtectionFile, FILE_WRITE);
  if (!file) {
    return false;
  }
  ProtectionFileState state{
      static_cast<uint8_t>(protectionLockedCached ? 1 : 0),
      static_cast<uint8_t>(pendingBrownoutError ? 1 : 0),
      static_cast<uint8_t>(pendingLowBatteryError ? 1 : 0),
  };
  const bool ok =
      file.write(reinterpret_cast<const uint8_t *>(&state), sizeof(state)) == sizeof(state);
  file.close();
  return ok;
}

void loadNextSequence() {
  File file = LittleFS.open(RecordsFile, FILE_READ);
  if (!file) {
    nextSequence = 1;
    return;
  }
  size_t size = file.size();
  if (size >= sizeof(ReadingRecord)) {
    file.seek(size - sizeof(ReadingRecord), SeekSet);
    ReadingRecord lastRecord;
    file.read(reinterpret_cast<uint8_t*>(&lastRecord), sizeof(ReadingRecord));
    if (lastRecord.crc == objectCrc(lastRecord)) {
      nextSequence = lastRecord.sequence + 1;
    }
  }
  file.close();
}

void hexdumpFile(Stream &stream, const char *path) {
  File file = LittleFS.open(path, FILE_READ);
  if (!file) {
    return;
  }

  const size_t size = file.size();
  stream.printf("%s (%u bytes):\n", path, static_cast<unsigned>(size));

  size_t offset = 0;
  uint8_t buf[16];
  while (file.available()) {
    const size_t n = file.read(buf, sizeof(buf));
    if (n == 0) {
      break;
    }

    stream.printf("%08x  ", static_cast<unsigned>(offset));

    size_t hexLen = 0;
    for (size_t i = 0; i < n; ++i) {
      if (i > 0) {
        stream.print(' ');
        ++hexLen;
      }
      stream.printf("%02x", buf[i]);
      hexLen += 2;
    }

    constexpr size_t hexWidth = 47;
    while (hexLen < hexWidth) {
      stream.print(' ');
      ++hexLen;
    }

    stream.print("  |");
    for (size_t i = 0; i < n; ++i) {
      const char c = static_cast<char>(buf[i]);
      stream.print((c >= 32 && c <= 126) ? c : '.');
    }
    for (size_t i = n; i < 16; ++i) {
      stream.print(' ');
    }
    stream.println("|");

    offset += n;
  }

  file.close();
}

bool scanMinSequence(uint32_t &minSequence) {
  minSequence = 0;

  File file = LittleFS.open(RecordsFile, FILE_READ);
  if (!file) {
    return false;
  }

  bool found = false;
  ReadingRecord record;
  while (file.read(reinterpret_cast<uint8_t*>(&record), sizeof(ReadingRecord)) == sizeof(ReadingRecord)) {
    if (record.crc != objectCrc(record)) {
      break;
    }
    if (!found || record.sequence < minSequence) {
      minSequence = record.sequence;
      found = true;
    }
  }
  file.close();
  return found;
}

// Recover from a /sync.dat pointer that no longer matches /records.bin.
void repairSyncState() {
  uint32_t minSequence = 0;
  if (!scanMinSequence(minSequence)) {
    return;
  }

  if (syncedThrough >= nextSequence) {
    syncedThrough = 0;
    saveSyncState();
    return;
  }

  if (minSequence <= syncedThrough) {
    compactRecords();
    loadNextSequence();
  }
}

} // namespace

void compactRecords() {
  File file = LittleFS.open(RecordsFile, FILE_READ);
  if (!file) return;

  File tmp = LittleFS.open("/tmp_records.bin", FILE_WRITE);
  if (!tmp) {
    file.close();
    return;
  }

  ReadingRecord record;
  while (file.read(reinterpret_cast<uint8_t*>(&record), sizeof(ReadingRecord)) == sizeof(ReadingRecord)) {
    if (record.sequence > syncedThrough) {
      tmp.write(reinterpret_cast<uint8_t*>(&record), sizeof(ReadingRecord));
    }
  }
  file.close();
  tmp.close();

  LittleFS.remove(RecordsFile);
  LittleFS.rename("/tmp_records.bin", RecordsFile);
}

bool begin() {
  if (!LittleFS.begin(true)) {
    initialized = false;
    return false;
  }
  initialized = true;
  loadSyncState();
  loadNextSequence();
  repairSyncState();
  loadStayAwakeState();
  loadProtectionState();
  return true;
}

bool available() {
  return initialized;
}

uint16_t currentPulses() {
  return rtcCurrentPulses;
}

uint32_t currentPeriodStart() {
  return rtcCurrentPeriodStart;
}

bool incrementCurrentPulse(uint32_t timestamp) {
  return addPulses(timestamp, 1);
}

bool addPulses(uint32_t timestamp, uint32_t count) {
  // Hot counters live in RTC RAM and must update even if LittleFS mount failed.
  if (count == 0) return true;
  if (rtcCurrentPeriodStart == 0) {
    rtcCurrentPeriodStart = timestamp;
  }
  const uint32_t next = static_cast<uint32_t>(rtcCurrentPulses) + count;
  rtcCurrentPulses = next > 0xFFFF ? 0xFFFF : static_cast<uint16_t>(next);
  return true;
}

bool rollCurrentPeriod(uint32_t timestamp, uint16_t batteryMv) {
  if (!initialized) {
    return false;
  }
  if (rtcCurrentPulses == 0) {
    rtcCurrentPeriodStart = timestamp;
    return true;
  }

  ReadingRecord record{
      nextSequence,
      rtcCurrentPeriodStart,
      rtcCurrentPulses,
      batteryMv,
      0,
      0,
  };
  record.crc = objectCrc(record);

  File file = LittleFS.open(RecordsFile, FILE_APPEND);
  if (!file) return false;
  file.write(reinterpret_cast<uint8_t*>(&record), sizeof(ReadingRecord));
  file.close();

  ++nextSequence;
  rtcCurrentPeriodStart = timestamp;
  rtcCurrentPulses = 0;
  return true;
}

bool loadUploadBatch(UploadBatch &batch) {
  batch = {};
  if (!initialized) {
    if (batch.errorCount < MaxUploadErrors) {
      batch.errors[batch.errorCount].code = "storage_unavailable";
      batch.errors[batch.errorCount].detail[0] = '\0';
      ++batch.errorCount;
    }
    return true;
  }

  File file = LittleFS.open(RecordsFile, FILE_READ);
  if (!file) {
    if (batch.errorCount < MaxUploadErrors) {
      batch.errors[batch.errorCount].code = "no_data";
      batch.errors[batch.errorCount].detail[0] = '\0';
      ++batch.errorCount;
    }
    return true;
  }

  ReadingRecord record;
  size_t offset = 0;
  if (file.size() >= sizeof(ReadingRecord) &&
      file.read(reinterpret_cast<uint8_t *>(&record), sizeof(ReadingRecord)) == sizeof(ReadingRecord)) {
    if (record.crc != objectCrc(record)) {
      if (batch.errorCount < MaxUploadErrors) {
        batch.errors[batch.errorCount].code = "crc_mismatch";
        snprintf(batch.errors[batch.errorCount].detail,
                 sizeof(batch.errors[batch.errorCount].detail),
                 "offset=%u",
                 0u);
        ++batch.errorCount;
      }
      file.close();
      return true;
    }
    if (record.sequence <= syncedThrough) {
      const uint32_t skip = syncedThrough - record.sequence + 1;
      offset = static_cast<size_t>(skip) * sizeof(ReadingRecord);
      if (offset >= file.size() || !file.seek(offset)) {
        file.close();
        if (batch.errorCount == 0) {
          batch.errors[batch.errorCount].code = "no_data";
          batch.errors[batch.errorCount].detail[0] = '\0';
          ++batch.errorCount;
        }
        return true;
      }
    } else if (!file.seek(0)) {
      file.close();
      if (batch.errorCount < MaxUploadErrors) {
        batch.errors[batch.errorCount].code = "storage_unavailable";
        batch.errors[batch.errorCount].detail[0] = '\0';
        ++batch.errorCount;
      }
      return true;
    } else {
      offset = 0;
    }
  }

  while (file.read(reinterpret_cast<uint8_t*>(&record), sizeof(ReadingRecord)) == sizeof(ReadingRecord)) {
    if (record.crc != objectCrc(record)) {
      if (batch.errorCount < MaxUploadErrors) {
        batch.errors[batch.errorCount].code = "crc_mismatch";
        snprintf(batch.errors[batch.errorCount].detail,
                 sizeof(batch.errors[batch.errorCount].detail),
                 "offset=%u",
                 static_cast<unsigned>(offset));
        ++batch.errorCount;
      }
      break;
    }

    if (record.sequence > syncedThrough) {
      if (batch.count < MaxUploadRecords) {
        batch.records[batch.count++] = record;
        batch.newestSequence = record.sequence;
      } else {
        batch.truncated = true;
        if (batch.errorCount < MaxUploadErrors) {
          batch.errors[batch.errorCount].code = "batch_truncated";
          batch.errors[batch.errorCount].detail[0] = '\0';
          ++batch.errorCount;
        }
        break;
      }
    }
    offset += sizeof(ReadingRecord);
  }
  file.close();

  if (batch.count == 0 && batch.errorCount == 0) {
    batch.errors[batch.errorCount].code = "no_data";
    batch.errors[batch.errorCount].detail[0] = '\0';
    ++batch.errorCount;
  }
  return true;
}

bool markSyncedThrough(uint32_t sequence) {
  if (!initialized) {
    return false;
  }
  if (sequence > syncedThrough && sequence < nextSequence) {
    syncedThrough = sequence;
    saveSyncState();
  }
  return true;
}

uint32_t unsyncedCount() {
  if (!initialized) {
    return 0;
  }
  if (nextSequence == 0 || nextSequence - 1 <= syncedThrough) return 0;
  return (nextSequence - 1) - syncedThrough;
}

bool stayAwakeBoot() {
  return stayAwakeBootCached;
}

bool setStayAwakeBoot(bool enabled) {
  stayAwakeBootCached = enabled;
  if (!initialized) {
    return false;
  }
  return saveStayAwakeState();
}

bool protectionLocked() {
  return protectionLockedCached;
}

bool setProtectionLocked(bool locked) {
  protectionLockedCached = locked;
  if (!initialized) {
    return false;
  }
  return saveProtectionState();
}

void markProtectionPendingBrownout() {
  pendingBrownoutError = true;
  if (initialized) {
    saveProtectionState();
  }
}

void markProtectionPendingLowBattery() {
  pendingLowBatteryError = true;
  if (initialized) {
    saveProtectionState();
  }
}

void attachPendingProtectionErrors(UploadBatch &batch) {
  if (pendingBrownoutError && batch.errorCount < MaxUploadErrors) {
    batch.errors[batch.errorCount].code = "brownout_lock";
    batch.errors[batch.errorCount].detail[0] = '\0';
    ++batch.errorCount;
  }
  if (pendingLowBatteryError && batch.errorCount < MaxUploadErrors) {
    batch.errors[batch.errorCount].code = "low_battery";
    batch.errors[batch.errorCount].detail[0] = '\0';
    ++batch.errorCount;
  }
}

void clearPendingProtectionErrors() {
  if (!pendingBrownoutError && !pendingLowBatteryError) {
    return;
  }
  pendingBrownoutError = false;
  pendingLowBatteryError = false;
  if (initialized) {
    saveProtectionState();
  }
}

void hexdump(Stream &stream) {
  if (!initialized) {
    stream.println("storage unavailable");
    return;
  }
  hexdumpFile(stream, RecordsFile);
  hexdumpFile(stream, SyncFile);
  hexdumpFile(stream, StayAwakeFile);
  hexdumpFile(stream, ProtectionFile);
}

void clear() {
  if (!initialized) {
    nextSequence = 1;
    syncedThrough = 0;
    stayAwakeBootCached = config::StayAwakeBoot;
    protectionLockedCached = false;
    pendingBrownoutError = false;
    pendingLowBatteryError = false;
    rtcCurrentPeriodStart = 0;
    rtcCurrentPulses = 0;
    return;
  }
  LittleFS.remove(RecordsFile);
  LittleFS.remove(SyncFile);
  LittleFS.remove(StayAwakeFile);
  LittleFS.remove(ProtectionFile);
  LittleFS.remove("/tmp_records.bin");
  nextSequence = 1;
  syncedThrough = 0;
  stayAwakeBootCached = config::StayAwakeBoot;
  protectionLockedCached = false;
  pendingBrownoutError = false;
  pendingLowBatteryError = false;
  rtcCurrentPeriodStart = 0;
  rtcCurrentPulses = 0;
}

} // namespace storage
