---
name: Serial fill records
overview: Add a diagnostics REPL `f`/`fill` command that appends synthetic LittleFS records (default 100) with random pulse counts 1–100, using the existing storage roll path.
todos:
  - id: add-fill-cmd
    content: Add f/fill REPL branch in handleDiagnosticsBoot (default 100, optional N, random pulses 1-100)
    status: completed
  - id: update-help
    content: Update REPL help string to include fill
    status: completed
  - id: sync-fw-spec
    content: Spawn SoT subagent to update fw_specification.md US-6 for fill command
    status: completed
isProject: false
---

# Serial fill-records command

## Behavior

In the stay-awake diagnostics REPL ([src/main.cpp](src/main.cpp) `handleDiagnosticsBoot`):

| Input | Effect |
| --- | --- |
| `f` / `fill` | Append **100** rolled records |
| `f 50` / `fill 50` | Append **N** records (N from optional argument) |

Each record gets a **random pulse count in 1–100** (inclusive) so every period actually appends (`rollCurrentPeriod` skips empty hot periods). Period starts are spaced by `config::RtcWakeIntervalSeconds`, ending just before “now”, so upload JSON timestamps look realistic.

Print `filled N records` (or an error if LittleFS/`roll` fails). Cap N at **500** to avoid long LittleFS stalls; reject `0` with a short usage line.

## Implementation (firmware only)

Extend the command `if/else` in [`handleDiagnosticsBoot()`](src/main.cpp) (~line 642) with `first == 'f'`, and update the help string on line 601.

Use existing APIs only (no new storage surface):

```cpp
flushAwakePulses(true);
// sample battery once → mV via reading.volts * 1000
// if hot pulses > 0: rollCurrentPeriod(now) to close open period
// rollCurrentPeriod(base) with 0 pulses → set hot periodStart = base (no append)
for i in 0..N-1:
  addPulses(base + i * interval, random(1, 101))
  rollCurrentPeriod(base + (i + 1) * interval, batteryMv)
```

The zero-pulse roll before the loop is required: after a normal roll, `rtcCurrentPeriodStart` is non-zero and `addPulses` will not overwrite it ([storage.cpp](src/storage.cpp) `addPulses` / `rollCurrentPeriod`).

```mermaid
flowchart LR
  REPL["f / fill N"] --> Flush["flushAwakePulses"]
  Flush --> Align["zero-pulse roll to base"]
  Align --> Loop["N x addPulses + roll"]
  Loop --> FS["/records.bin append"]
```

## Docs

After code lands, spawn the SoT sync subagent to update US-6 in [docs/firmware/fw_specification.md](docs/firmware/fw_specification.md) (new `f`/`fill` row + help-line mention). No intent_spec or upload API change.