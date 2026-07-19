#include "storage.h"

#include <LittleFS.h>
#include <FS.h>

namespace storage {

namespace {

RTC_DATA_ATTR uint32_t rtcCurrentPeriodStart = 0;
RTC_DATA_ATTR uint32_t rtcCurrentPulses = 0;

uint32_t nextSequence = 1;
uint32_t syncedThrough = 0;

const char *RecordsFile = "/records.bin";
const char *SyncFile = "/sync.dat";

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

} // namespace

bool begin() {
  if (!LittleFS.begin(true)) {
    return false;
  }
  loadSyncState();
  loadNextSequence();
  return true;
}

bool incrementCurrentPulse(uint32_t timestamp) {
  return addPulses(timestamp, 1);
}

bool addPulses(uint32_t timestamp, uint32_t count) {
  if (count == 0) return true;
  if (rtcCurrentPeriodStart == 0) {
    rtcCurrentPeriodStart = timestamp;
  }
  rtcCurrentPulses += count;
  return true;
}

bool rollCurrentPeriod(uint32_t timestamp, uint16_t batteryMv) {
  if (rtcCurrentPulses == 0) {
    rtcCurrentPeriodStart = timestamp;
    return true;
  }

  ReadingRecord record{
      nextSequence,
      rtcCurrentPeriodStart,
      timestamp,
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
  File file = LittleFS.open(RecordsFile, FILE_READ);
  if (!file) return true;

  ReadingRecord record;
  while (file.read(reinterpret_cast<uint8_t*>(&record), sizeof(ReadingRecord)) == sizeof(ReadingRecord)) {
    if (record.crc == objectCrc(record) && record.sequence > syncedThrough) {
      if (batch.count < MaxUploadRecords) {
        batch.records[batch.count++] = record;
        batch.newestSequence = record.sequence;
      } else {
        break;
      }
    }
  }
  file.close();
  return true;
}

bool markSyncedThrough(uint32_t sequence) {
  if (sequence > syncedThrough && sequence < nextSequence) {
    syncedThrough = sequence;
    saveSyncState();
    compactRecords();
  }
  return true;
}

uint32_t unsyncedCount() {
  if (nextSequence == 0 || nextSequence - 1 <= syncedThrough) return 0;
  return (nextSequence - 1) - syncedThrough;
}

void dump(Stream &stream) {
  stream.printf("storage next=%lu synced=%lu rtc_start=%lu rtc_pulses=%lu unsynced=%lu\n",
                static_cast<unsigned long>(nextSequence),
                static_cast<unsigned long>(syncedThrough),
                static_cast<unsigned long>(rtcCurrentPeriodStart),
                static_cast<unsigned long>(rtcCurrentPulses),
                static_cast<unsigned long>(unsyncedCount()));
}

void clear() {
  LittleFS.remove(RecordsFile);
  LittleFS.remove(SyncFile);
  LittleFS.remove("/tmp_records.bin");
  nextSequence = 1;
  syncedThrough = 0;
  rtcCurrentPeriodStart = 0;
  rtcCurrentPulses = 0;
}

} // namespace storage
