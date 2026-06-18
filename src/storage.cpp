#include "storage.h"

namespace storage {

namespace {

constexpr uint8_t EepromAddress = 0x57;
constexpr uint16_t EepromSize = 4096;
constexpr uint16_t PageSize = 32;
constexpr uint32_t Magic = 0x4D425544UL; // MBUD
constexpr uint16_t Version = 1;
constexpr uint16_t HeaderAddress = 0;
constexpr uint16_t RecordsAddress = 64;
constexpr uint8_t RecordCount = (EepromSize - RecordsAddress) / sizeof(ReadingRecord);

struct __attribute__((packed)) Header {
  uint32_t magic;
  uint16_t version;
  uint16_t recordSize;
  uint32_t nextSequence;
  uint32_t syncedThrough;
  uint32_t currentPeriodStart;
  uint32_t currentPulses;
  uint16_t crc;
};

TwoWire *bus = nullptr;
Header header{};

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

bool readBytes(uint16_t address, uint8_t *data, size_t len) {
  while (len > 0) {
    const uint8_t chunk = static_cast<uint8_t>(min<size_t>(len, 28));
    bus->beginTransmission(EepromAddress);
    bus->write(static_cast<uint8_t>(address >> 8));
    bus->write(static_cast<uint8_t>(address & 0xFF));
    if (bus->endTransmission(false) != 0) {
      return false;
    }
    if (bus->requestFrom(EepromAddress, chunk) != chunk) {
      return false;
    }
    for (uint8_t i = 0; i < chunk; ++i) {
      data[i] = bus->read();
    }
    data += chunk;
    address += chunk;
    len -= chunk;
  }
  return true;
}

bool writeBytes(uint16_t address, const uint8_t *data, size_t len) {
  while (len > 0) {
    const uint8_t pageRemaining = PageSize - (address % PageSize);
    const uint8_t chunk = static_cast<uint8_t>(min<size_t>(len, pageRemaining));
    bus->beginTransmission(EepromAddress);
    bus->write(static_cast<uint8_t>(address >> 8));
    bus->write(static_cast<uint8_t>(address & 0xFF));
    for (uint8_t i = 0; i < chunk; ++i) {
      bus->write(data[i]);
    }
    if (bus->endTransmission() != 0) {
      return false;
    }
    delay(6);
    data += chunk;
    address += chunk;
    len -= chunk;
  }
  return true;
}

template <typename T> bool readObject(uint16_t address, T &value) {
  return readBytes(address, reinterpret_cast<uint8_t *>(&value), sizeof(T));
}

template <typename T> bool writeObject(uint16_t address, T &value) {
  value.crc = objectCrc(value);
  return writeBytes(address, reinterpret_cast<const uint8_t *>(&value), sizeof(T));
}

uint16_t recordAddress(uint8_t slot) {
  return RecordsAddress + static_cast<uint16_t>(slot) * sizeof(ReadingRecord);
}

bool validHeader(const Header &candidate) {
  return candidate.magic == Magic && candidate.version == Version &&
         candidate.recordSize == sizeof(ReadingRecord) &&
         candidate.crc == objectCrc(candidate);
}

bool validRecord(const ReadingRecord &record) {
  return record.sequence > 0 && record.crc == objectCrc(record);
}

bool saveHeader() {
  return writeObject(HeaderAddress, header);
}

bool appendRecord(const ReadingRecord &input) {
  ReadingRecord record = input;
  const uint8_t slot = (record.sequence - 1) % RecordCount;
  return writeObject(recordAddress(slot), record);
}

} // namespace

bool begin(TwoWire &wire) {
  bus = &wire;

  Header candidate{};
  if (!readObject(HeaderAddress, candidate) || !validHeader(candidate)) {
    header = {
        Magic,
        Version,
        sizeof(ReadingRecord),
        1,
        0,
        0,
        0,
        0,
    };
    return saveHeader();
  }

  header = candidate;
  return true;
}

bool incrementCurrentPulse(uint32_t timestamp) {
  return addPulses(timestamp, 1);
}

bool addPulses(uint32_t timestamp, uint32_t count) {
  if (count == 0) {
    return true;
  }
  if (header.currentPeriodStart == 0) {
    header.currentPeriodStart = timestamp;
  }
  header.currentPulses += count;
  return saveHeader();
}

bool rollCurrentPeriod(uint32_t timestamp, uint16_t batteryMv) {
  if (header.currentPulses == 0) {
    header.currentPeriodStart = timestamp;
    return saveHeader();
  }

  ReadingRecord record{
      header.nextSequence,
      header.currentPeriodStart,
      timestamp,
      header.currentPulses,
      batteryMv,
      0,
      0,
  };

  if (!appendRecord(record)) {
    return false;
  }

  ++header.nextSequence;
  header.currentPeriodStart = timestamp;
  header.currentPulses = 0;
  return saveHeader();
}

bool loadUploadBatch(UploadBatch &batch) {
  batch = {};
  const uint32_t first = header.syncedThrough + 1;
  const uint32_t last = header.nextSequence > 0 ? header.nextSequence - 1 : 0;
  if (first > last) {
    return true;
  }

  for (uint32_t sequence = first; sequence <= last && batch.count < MaxUploadRecords; ++sequence) {
    ReadingRecord record{};
    const uint8_t slot = (sequence - 1) % RecordCount;
    if (!readObject(recordAddress(slot), record) || !validRecord(record) ||
        record.sequence != sequence) {
      continue;
    }

    batch.records[batch.count++] = record;
    batch.newestSequence = record.sequence;
  }

  return true;
}

bool markSyncedThrough(uint32_t sequence) {
  if (sequence > header.syncedThrough && sequence < header.nextSequence) {
    header.syncedThrough = sequence;
    return saveHeader();
  }
  return true;
}

uint32_t unsyncedCount() {
  if (header.nextSequence == 0 || header.nextSequence - 1 <= header.syncedThrough) {
    return 0;
  }
  return (header.nextSequence - 1) - header.syncedThrough;
}

void dump(Stream &stream) {
  stream.printf("storage next=%lu synced=%lu current_start=%lu current_pulses=%lu unsynced=%lu\n",
                static_cast<unsigned long>(header.nextSequence),
                static_cast<unsigned long>(header.syncedThrough),
                static_cast<unsigned long>(header.currentPeriodStart),
                static_cast<unsigned long>(header.currentPulses),
                static_cast<unsigned long>(unsyncedCount()));
}

} // namespace storage
