#pragma once

#include <Arduino.h>

namespace storage {

constexpr uint8_t MaxUploadRecords = 48;
constexpr uint8_t MaxUploadErrors = 8;

struct __attribute__((packed)) ReadingRecord {
  uint32_t sequence;
  uint32_t periodStart;
  uint16_t pulses;
  uint16_t batteryMv;
  uint16_t flags;
  uint16_t crc;
};

struct UploadError {
  const char *code;
  char detail[40];
};

struct UploadBatch {
  ReadingRecord records[MaxUploadRecords];
  uint8_t count;
  uint32_t newestSequence;
  UploadError errors[MaxUploadErrors];
  uint8_t errorCount;
  bool truncated;
};

bool begin();
bool incrementCurrentPulse(uint32_t timestamp);
bool addPulses(uint32_t timestamp, uint32_t count);
bool rollCurrentPeriod(uint32_t timestamp, uint16_t batteryMv);
bool loadUploadBatch(UploadBatch &batch);
bool markSyncedThrough(uint32_t sequence);
uint32_t unsyncedCount();
bool stayAwakeBoot();
bool setStayAwakeBoot(bool enabled);
void dump(Stream &stream);
void clear();

} // namespace storage
