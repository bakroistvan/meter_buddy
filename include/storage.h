#pragma once

#include "config.h"

namespace storage {

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
  ReadingRecord records[config::MaxUploadRecords];
  uint8_t count;
  uint32_t newestSequence;
  UploadError errors[config::MaxUploadErrors];
  uint8_t errorCount;
  bool truncated;
};

bool begin();
bool available();
uint16_t currentPulses();
uint32_t currentPeriodStart();
bool incrementCurrentPulse(uint32_t timestamp);
bool addPulses(uint32_t timestamp, uint32_t count);
bool rollCurrentPeriod(uint32_t timestamp, uint16_t batteryMv);
bool loadUploadBatch(UploadBatch &batch);
bool markSyncedThrough(uint32_t sequence);
void compactRecords();
uint32_t unsyncedCount();
bool stayAwakeBoot();
bool setStayAwakeBoot(bool enabled);

// Button-only protection sleep (brown-out / low battery). Survives power loss.
bool protectionLocked();
bool setProtectionLocked(bool locked);
void markProtectionPendingBrownout();
void markProtectionPendingLowBattery();
void attachPendingProtectionErrors(UploadBatch &batch);
void clearPendingProtectionErrors();

void hexdump(Stream &stream);
void clear();

} // namespace storage
