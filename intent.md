# meter_buddy — Design Intent

## Purpose

meter_buddy is a battery-powered device that attaches to a utility electricity meter and
silently records energy consumption over time. It works by counting the optical pulses that
modern meters emit proportionally to energy use, accumulating them into periodic readings,
and periodically uploading those readings to a backend service for storage and analysis.

The device is intended to run unattended for extended periods (weeks to months) between
manual interventions, requiring only occasional button presses to trigger uploads.

---

## Core Goals

1. **Long battery life.** The device spends the overwhelming majority of its time in the
   deepest available sleep state. It wakes only when a pulse arrives, when a periodic
   housekeeping timer fires, or when the user presses the upload button.

2. **No data loss.** Every pulse that arrives must be counted and persisted before the
   device returns to sleep. Power loss at any point — including mid-write — must not
   corrupt previously stored data. Unuploaded records must survive indefinitely until a
   successful upload occurs.

3. **Self-healing.** The device recovers gracefully from unexpected reboots, brown-outs,
   and clock drift without requiring user intervention.

4. **Simple operation.** A single button covers all user-facing interactions: a short
   press triggers an upload; a long press enters a diagnostic/maintenance mode.

---

## Measurement Model

- The meter emits pulses proportional to energy consumed (configurable impulses per kWh).
- Pulses are accumulated over fixed-length time windows (currently 60 seconds).
- At the end of each window a single record is stored: timestamp, pulse count, battery voltage.
- Time resolution is therefore one record per window. The minimum measurable power is
  one pulse per window; below that threshold consumption appears as zero.
- Power for a window can be derived from the pulse count, the window duration, and the
  meter's impulse rate.

---

## Storage Architecture Intent

### Two concerns, two lifetimes

There are two distinct storage concerns:

- **Hot accumulation:** the pulse count and start time of the *current, incomplete* window.
  This changes on every pulse and must be persisted quickly, but its loss on power failure
  is acceptable (at most one window of data, typically 60 seconds).

- **Committed records:** completed windows that have not yet been uploaded. These must
  survive indefinitely, including complete power loss. Loss of committed records is not
  acceptable.

A good design separates these two concerns into storage layers with different durability
and write-frequency characteristics.

### Bounded history window

The device does not need to store unlimited history. Uploads happen opportunistically
when the user presses the button. A history window of several days is sufficient to
tolerate extended periods of Wi-Fi unavailability or user absence.

Once a record has been successfully acknowledged by the backend it can be discarded.

### Write endurance

Storage that is written on every single pulse is subject to wear proportional to the
meter's pulse rate. At typical household consumption rates this can be thousands of
writes per day to the same physical location. Storage chosen for frequently-mutating
state must either have high endurance, distribute writes across a larger area, or be
avoided entirely for that purpose.

Committed records, by contrast, are written only once per time window (once per minute)
and read at most a handful of times before being discarded. Their write rate is low and
predictable regardless of power consumption.

### Overflow and resilience

If committed records accumulate faster than they are uploaded — because uploads fail or
are infrequent — the storage backing them must not silently discard data. When the
rolling window of recent records approaches capacity, older unuploaded records must be
moved to a secondary store that retains them until the next successful upload clears them.

---

## Upload Model

- Uploads are triggered manually by the user pressing the button.
- On upload: connect to Wi-Fi, synchronise the clock from the network, POST a batch of
  records to the backend, then disconnect.
- Records are uploaded in bounded batches. If more records exist than fit in one batch,
  subsequent uploads drain the remainder.
- An upload is only considered successful when the backend acknowledges it (HTTP 200/201).
  On any failure the records are retained for the next attempt.
- The device must never delete a record it has not received acknowledgement for.

---

## Diagnostics and Observability

- Serial output provides a real-time view of device state during development and
  troubleshooting (can be disabled for production builds to save power).
- A long button press enters a diagnostic mode: the device stays awake, logs pulses in
  real time, and accepts serial commands to inspect or clear stored data.
- The LED gives coarse feedback: blink patterns distinguish pulse events, RTC rolls,
  upload outcomes, and diagnostic mode entry.

---

## Constraints and Non-Goals

- **No OTA updates.** Firmware is updated by physically connecting the device via USB.
  This simplifies the flash layout and removes the need for a redundant firmware partition.
- **No real-time display.** All data is consumed by the backend; the device has no screen.
- **No sub-minute resolution.** The 60-second window is a deliberate trade-off between
  granularity and storage/battery efficiency. Finer resolution would require more records,
  more writes, and more wake events.
- **Single-phase, single-meter.** The device is designed for one meter, one sensor.
