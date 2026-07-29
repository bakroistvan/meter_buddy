#pragma once

#include <Arduino.h>

namespace storage {

constexpr uint8_t MaxUploadRecords = 48;

struct __attribute__((packed)) ReadingRecord {
  uint32_t sequence;
  uint32_t periodStart;
  uint16_t pulses;
  uint16_t batteryMv;
  uint16_t flags;
  uint16_t crc;
};

struct UploadBatch {
  ReadingRecord records[MaxUploadRecords];
  uint8_t count;
  uint32_t newestSequence;
};

bool begin();
bool incrementCurrentPulse(uint32_t timestamp);
bool addPulses(uint32_t timestamp, uint32_t count);
bool rollCurrentPeriod(uint32_t timestamp, uint16_t batteryMv);
bool loadUploadBatch(UploadBatch &batch);
bool markSyncedThrough(uint32_t sequence);
uint32_t unsyncedCount();
void dump(Stream &stream);
void clear();

} // namespace storage
