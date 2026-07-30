---
name: SoT gap fixes
overview: Update the SoT docs (`intent_spec.md` + `fw_specification.md`) for I2/I3/I5, code-backed wiring W1–W13, and F2; drop other gaps; archive the five superseded old docs under docs/archive/.
todos:
  - id: intent-i2-i3-i5
    content: Update intent_spec.md for I2 indefinite retention, I3 write-endurance, I5 optional OTA clarity
    status: completed
  - id: fw-hardware
    content: Add Hardware assumptions section to fw_specification.md (W1–W13 per code audit)
    status: completed
  - id: fw-f2-i3
    content: Document F2 compaction + brief I3 RTC-RAM endurance note in fw_specification.md
    status: completed
  - id: archive-old-docs
    content: Move five superseded docs into docs/archive/; fix README and inbound links
    status: completed
  - id: docs-readme-sot
    content: Declare SoT in docs/README.md; list archived docs under Archive
    status: completed
isProject: false
---

# SoT gap fixes

## Decisions (locked)

| ID | Action |
| --- | --- |
| I2, I3, I5 | **Add** to SoT |
| F2 | **Add** to [fw_specification.md](docs/firmware/fw_specification.md) |
| W1–W13 | **Add based on code audit** (below) |
| All unmentioned gaps (I1, I4, I6, I7, A1–A11, T1, T2, F1, F3, F4) | **Drop** — do not carry into SoT |
| Old five docs | **Archive** under [docs/archive/](docs/archive/) (not leave as living docs) |

SoT remains: [docs/intent_spec.md](docs/intent_spec.md) + [docs/firmware/fw_specification.md](docs/firmware/fw_specification.md).

## Wiring filter (subagent vs code)

**Into fw_spec (code-confirmed / firmware-dependent):**

- **W1** TEMT6000 as pulse sensor — [include/pins.h](include/pins.h)
- **W2** I2C D4=SDA, D5=SCL — pins.h + `Wire.begin`
- **W3** 3V3 powers DS3231 + TEMT6000; common GND — pins.h always-on note + wiring topology as hardware assumption
- **W5** TEMT6000 always-on 3V3 (not GPIO-switched) — pins.h + deep-sleep GPIO wake
- **W8** Button `INPUT_PULLUP`, no external pull-up — [src/main.cpp](src/main.cpp) `initWakePinsAndLed`
- **W9 (code part)** Battery on A0 with **1:2** scale — [src/battery.cpp](src/battery.cpp) `* 2.0f`

**Brief hardware assumptions in fw_spec (doc/README, not encoded as constants):**

- **W4** LiPo + TP4056 → BAT+/GND
- **W6** Breakout may include AT24C32; **FW does not use it** (LittleFS only)
- **W7** Optional 4.7k I2C pull-ups if breakout lacks them
- **W9 (values)** 200k/200k preferred (220k OK), 1% — matches 1:2 assumption
- **W10** A0/GPIO2 strapping: divider must not hold pin LOW at boot
- **W11** TP4056 RPROG ~400 mA mod
- **W12** Series resistors on LED anodes
- **W13** Build prep checklist (desolder RTC power LED, shield TEMT6000, accessible button, meter check before battery)

Strip stale RISING/`ext0` language if any text is copied from [wiring.md](docs/firmware/wiring.md); SoT wake remains GPIO_LOW / FALLING ISR.

## Edits

### 1. [docs/intent_spec.md](docs/intent_spec.md)

- **I2:** Change N-3 from “several days” to **indefinite retention of unacknowledged records until successful upload** (flash capacity still practical limit; do not promise silent discard). Align any acceptance row that cited “several days.”
- **I3:** Add requirement under storage/quality: hot accumulation must avoid wear-prone storage on every pulse (high-endurance / distribute / avoid flash for hot state).
- **I5:** Keep optional OTA after successful data upload (P-8 / N-4) — already present; tighten wording so USB flash remains primary and network OTA is allowed, not forbidden.

### 2. [docs/firmware/fw_specification.md](docs/firmware/fw_specification.md)

- New **Hardware assumptions** section: pin table expanded with I2C D4/D5, Battery A0, TEMT6000, always-on 3V3 + common GND, INPUT_PULLUP button, battery 1:2 (+ resistor note), brief W4/W6–W13 bullets; AT24C32 unused.
- **F2:** In upload/storage §6 (and storage model if needed): after HTTP 200/201 with `batch.count > 0`, `markSyncedThrough` advances sync cursor then **`compactRecords()`** rewrites `/records.bin` to drop sequences ≤ syncedThrough. Note empty heartbeat does not compact; `repairSyncState` may also compact on boot mismatch.
- **I3 (brief):** One sentence that pulse wakes update RTC RAM hot counters, not LittleFS, for write endurance.
- **I5:** No change beyond ensuring US-10 / OTA wording stays consistent with optional OTA.

### 3. Archive superseded docs

Move (git `mv`) these into [docs/archive/](docs/archive/), keeping filenames unless a clash forces a prefix:

| From | To |
| --- | --- |
| [docs/intent.md](docs/intent.md) | `docs/archive/intent.md` |
| [docs/architecture.md](docs/architecture.md) | `docs/archive/architecture.md` |
| [docs/firmware/wiring.md](docs/firmware/wiring.md) | `docs/archive/wiring.md` |
| [docs/firmware/timing.md](docs/firmware/timing.md) | `docs/archive/timing.md` |
| [docs/firmware/input_flows.md](docs/firmware/input_flows.md) | `docs/archive/input_flows.md` |

Then:

- Grep the repo for links to those paths; retarget living docs to SoT (or to `docs/archive/...` only where historical reference is intentional).
- Update [docs/README.md](docs/README.md): living table = SoT + [api/upload.md](docs/api/upload.md) (+ package READMEs); Archive section lists the five moved files as non-normative history.
- Note in README that monorepo/backend layout formerly in `architecture.md` is historical; current backend setup stays in [backend/README.md](backend/README.md) and [docs/api/upload.md](docs/api/upload.md).

### 4. [docs/README.md](docs/README.md)

- Declare **intent_spec + fw_specification are the single source of truth** for product requirements and firmware behavior.
- Remove the five files from the living-docs table; list them under Archive only.

## Out of scope

- No C++ changes.
- Dropped gaps stay out (batch size 48, loop delay 50, mid-write atomicity, secondary overflow store, monorepo/backend fold-in, etc.).
- No rewrite of archived content beyond the move + link fixes.