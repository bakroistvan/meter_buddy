# Meter Buddy — Intent Specification (User Requirements)

**Status:** requirements only. No pin maps, libraries, storage media, protocols, or other implementation choices.  
**Derived from / paired with:** [firmware/fw_specification.md](firmware/fw_specification.md) (how firmware realizes these intents today).  
**Historical product notes:** [archive/intent.md](archive/intent.md) (non-normative).

This document states **what users and operators need the device to do**. Solutions may change; these intents should remain stable unless the product goals change.

Together with [firmware/fw_specification.md](firmware/fw_specification.md), this is the **single source of truth** for product requirements and firmware behavior.

---

## 1. Product purpose

1. The device attaches to a utility electricity meter and records energy use by counting the meter’s optical pulses.
2. It runs unattended for long periods on battery, with rare manual interaction.
3. Recorded consumption is uploaded to a backend for storage and analysis when the user requests it.

---

## 2. Core quality goals

| ID | Requirement |
| --- | --- |
| Q-1 | **Battery life:** The device must spend almost all time in the deepest practical sleep, waking only for meter pulses, periodic housekeeping, or user action. |
| Q-2 | **Pulse integrity:** Every accepted meter pulse must be counted before returning to sleep. Counting into the current incomplete window must not depend on durable/flash storage being mounted or writable; only committing a completed period requires durable storage. |
| Q-3 | **Committed durability:** Completed measurement periods that have not been acknowledged by the backend must survive power loss and remain until a successful upload. |
| Q-4 | **Hot-window tolerance:** Loss of the *current incomplete* period on sudden power cut is acceptable (at most one period of data). |
| Q-5 | **Self-healing:** Unexpected reboot, brown-out, and moderate clock drift must not require user repair for normal pulse counting and later upload. |
| Q-6 | **Simple UX:** A single button covers primary user actions (upload vs maintenance). |
| Q-7 | **Hot-state write endurance:** Frequently mutating pulse/window state must not be written to wear-prone storage on every pulse; use high-endurance memory, distribute writes, or avoid flash for that hot state. |

---

## 3. Measurement requirements

| ID | Requirement |
| --- | --- |
| M-1 | Pulses are proportional to energy; the meter’s impulses-per-kWh is a configured property of the installation. |
| M-2 | Pulses accumulate into fixed-length time windows (period length is a product parameter; currently one minute). |
| M-3 | At the end of each window with activity, one record exists: time, pulse count, and battery condition. |
| M-4 | Sub-period resolution is not required; one record per window is sufficient. |
| M-5 | Short isolated pulses must be recorded with minimal awake time. |
| M-6 | When pulses arrive in rapid succession, the device must still count them accurately (including while briefly staying awake), then return to sleep when the meter is quiet again. |
| M-7 | Battery condition written onto period records and the live sample attached to an upload must be taken with the radio quiet so Wi‑Fi activity does not skew the ADC; casual diagnostics inspection need not force that condition. |

**Reference meter constant:** The product default / reference installation assumes **1000 pulses per kWh** (`MeterImpulsesPerKwh = 1000`). Load ↔ pulse-interval and load ↔ 5-minute pulse-count conversion formulas are in [firmware/fw_specification.md](firmware/fw_specification.md) (Hardware assumptions → Meter constant).

---

## 4. Wake / event requirements

| ID | Requirement |
| --- | --- |
| W-1 | While asleep, the device must wake on: meter pulse, periodic housekeeping signal, and user button. |
| W-2 | After handling a wake, the device must return to sleep unless the user has requested continuous awake/diagnostics, or an attached debug host requires it on paths that evaluate that policy (cold boot / upload / long-press). Housekeeping and isolated pulse wakes may return to sleep even if a debug host is present. |
| W-3 | Housekeeping must close the current period (if any pulses), capture battery state, and arm the next housekeeping wake. |
| W-4 | When multiple wake reasons are pending at the same moment, the device must apply a deterministic priority so behavior is predictable. |
| W-5 | While a wake is being handled, additional events must not corrupt counts or storage; pulses that can be captured during a long handler (e.g. upload) should still be counted; events that cannot be handled concurrently may be deferred to a later opportunity without corrupting prior data. |
| W-6 | The device must not enter a tight re-wake loop from a held button or a still-asserted pulse line. |

---

## 5. User interaction requirements

| ID | Requirement |
| --- | --- |
| U-1 | **Short press:** Trigger upload of pending data (and a heartbeat even when there is nothing to send). |
| U-2 | **Long press:** Toggle “stay awake / diagnostics” without uploading. Newly **enabled** → remain/enter stay-awake; newly **disabled** → return to normal sleeping operation. |
| U-3 | Stay-awake mode keeps the device awake for inspection, live pulse indication, and operator commands over a serial console. |
| U-4 | The operator must be able to exit stay-awake and return the device to normal sleeping operation (long-press toggle off, or diagnostics serial command). |
| U-5 | With a debug host connected over USB serial, the device may remain awake for development without requiring the stay-awake flag. |
| U-6 | Visible indicators must distinguish at least: idle awake, pulse seen (~100 ms flash per accepted pulse, including during long blocking work such as upload), housekeeping, upload in progress, upload failure, stay-awake enabled, stay-awake disabled. |

---

## 6. Upload requirements

| ID | Requirement |
| --- | --- |
| P-1 | Uploads are initiated by the user (short press), not on a continuous network schedule. |
| P-2 | On upload, the device must fold any already-accepted pulses still only in volatile awake counting into the open period, close that period if needed, open one network session (connect once, refresh time from the network when possible), and send pending records as one or more POSTs on that session. Pulses accepted during the upload itself belong to the new open period, not the batch being posted. |
| P-3 | Records are sent in bounded batches; remaining records drain on later successful uploads. |
| P-4 | A record may be discarded locally only after the backend has acknowledged it. |
| P-5 | Network or protocol failure must retain records and give clear failure feedback. |
| P-6 | An empty successful heartbeat (nothing to upload) is allowed and is not treated as a user-facing failure. |
| P-7 | Upload attempts may report storage/integrity problems alongside readings so the backend and operator can see device health. |
| P-8 | After a successful upload that delivered readings, the device may check for a newer firmware image before releasing the upload network session, when connectivity still allows it. |

---

## 7. Diagnostics requirements

| ID | Requirement |
| --- | --- |
| D-1 | Operators can inspect stored records (raw durable-storage hex and the upload JSON body that would be POSTed), the open incomplete period (hot pulse count / period start), whether durable storage is available, unsynced record count, battery (voltage, estimate, and ADC calibration health), input levels, and time while awake. |
| D-2 | Operators can clear stored data when deliberately requested. |
| D-3 | Operators can force an upload and reboot from the console. |
| D-4 | Serial logging is available for troubleshooting and may be disabled in production builds to save power. |

---

## 8. Constraints and non-goals

| ID | Requirement |
| --- | --- |
| N-1 | No on-device display; the backend is the primary data consumer. |
| N-2 | Single meter, single optical sensor. |
| N-3 | Unacknowledged committed records must be retained on-device **indefinitely until a successful upload acknowledges them**. Flash capacity is a practical limit; the device must not silently discard unacked records to free space. |
| N-4 | **USB flashing is the primary** way to install firmware. **Network OTA is allowed** as an optional step after a successful data upload when connectivity still permits it — not forbidden. |
| N-5 | The backend must serve device ingest and all operator UI/admin endpoints over **HTTPS** with **authenticated** access; only a dedicated unauthenticated liveness probe (e.g. `GET /healthz`) is exempt. |

---

## 9. Acceptance mapping (intent → observable behavior)

| Intent | Observable acceptance |
| --- | --- |
| Q-1 / W-2 | After pulse or housekeeping, device returns to sleep unless stay-awake/USB applies. |
| Q-2 / Q-7 | Pulse wakes update hot counters without a durable-storage write per pulse, and without requiring durable storage to be available; roll/upload still need durable storage. |
| M-5 / M-6 | Isolated pulse increments by one; burst trains are fully counted then sleep after quiet. |
| W-4 / W-5 | Documented priority when button+RTC (+pulse) coincide; no corrupt records; deferred sources handled later. |
| U-1 / U-2 | Short press uploads; long press toggles stay-awake without upload (enable → stay awake; disable → sleep). |
| U-6 | Pulse LED ~100 ms flash per accepted pulse even during upload; status LED patterns for upload, housekeeping, stay-awake, and failure. |
| D-1 | Diagnostics `status` / `dump` expose storage health, open hot period, and rolled-only JSON readings. |
| P-4 / P-5 / N-3 | Failed upload leaves data; LED error pattern; retry succeeds later; unacked records not silently dropped. |
| P-6 | Empty heartbeat succeeds without error indication. |
| P-8 / N-4 | After successful upload with readings, OTA check may run before the upload network session is released; USB flash remains a valid install path. |
| N-5 | Upload ingest, dump browser UI, dump JSON, `/db`, and live WebSocket require HTTPS + credentials; `/healthz` alone is unauthenticated. |

When firmware behavior and [fw_specification.md](firmware/fw_specification.md) disagree with this intent, **intent wins for product decisions**; when they disagree only on how something is implemented, **fw_specification + code** win until intent is consciously revised.
