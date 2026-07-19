# Timing State Machine

```mermaid
stateDiagram-v2
    state "Deep Sleep" as SLEEP
    state "handlePulseWake" as PULSE_WAKE
    state "countAwakeUntilQuiet" as COUNT_AWAKE
    state "handleRtcWake" as RTC_WAKE
    state "handleUploadWake" as UPLOAD_WAKE
    state "loop() while awake\n(no deep sleep)" as LOOP_AWAKE

    SLEEP --> PULSE_WAKE : GPIO4 HIGH
    SLEEP --> RTC_WAKE : GPIO5 LOW (RTC alarm)
    SLEEP --> UPLOAD_WAKE : GPIO21 LOW (button)
    SLEEP --> LOOP_AWAKE : power-on cold boot\n(deep sleep disabled)

    PULSE_WAKE --> SLEEP : timestamp <= lastPulseWakeUnix\n→ re-wake, discard

    PULSE_WAKE --> PULSE_WAKE_DECIDE : timestamp advanced

    state "Decide: isolated or burst?" as PULSE_WAKE_DECIDE
    PULSE_WAKE_DECIDE --> SLEEP : interval > PulseAwakeThresholdMs 8000ms\n→ isolated: count 1, sleep
    PULSE_WAKE_DECIDE --> COUNT_AWAKE : interval ≤ PulseAwakeThresholdMs 8000ms\n→ burst: stay up & accumulate

    COUNT_AWAKE --> SLEEP : done (return total count)

    RTC_WAKE --> SLEEP : roll period, schedule next alarm

    UPLOAD_WAKE --> SLEEP : upload batch, sleep

    LOOP_AWAKE --> LOOP_AWAKE : poll controls, flush pulses, keep WiFi
```

```mermaid
stateDiagram-v2
    state "countAwakeUntilQuiet" as C {

        state "Settle" as SETTLE : wait up to\nPulseDebounceMs × 4\n= 200ms\nfor GPIO4 to go LOW
        state "Accumulate" as ACCUM : attach RISING interrupt\ncount pulses via ISR
        state "Exit decision" as EXIT

        [*] --> SETTLE
        SETTLE --> ACCUM
        ACCUM --> EXIT

        EXIT --> ACCUM : time since last pulse\n< PulseAwakeQuietMs 30000ms\nand total elapsed\n< PulseAwakeMaxMs 300000ms
        EXIT --> [*] : quiet for\n≥ PulseAwakeQuietMs 30000ms\nor ≥ PulseAwakeMaxMs 300000ms\n→ detach interrupt,\nreturn count
    }

    note right of ACCUM
        ISR debounce: ignores edges
        closer than PulseDebounceMs (50ms)
    end note
```

```mermaid
stateDiagram-v2
    state "loop()" as LOOP_DETAIL {

        state "flushAwakePulses()" as FLUSH : every AwakePulseFlushMs 5000ms\n→ write accumulated pulses\nto EEPROM
        state "keepWifiConnected()" as WIFI : every WifiReconnectIntervalMs 10000ms\n→ reconnect if disconnected
        state "pollAwakeControls()" as POLL : check upload button,\ncheck RTC pin state

        [*] --> FLUSH
        FLUSH --> WIFI
        WIFI --> POLL
        POLL --> [*] : delay(50)
    }
```

## Timing Parameters

| Constant | Value | Role |
|---|---|---|
| `PulseDebounceMs` | 50 ms | Minimum interval between valid RISING edges (ISR filter) |
| `PulseDebounceMs × 4` | 200 ms | Settle timeout: wait for pin to go LOW before attaching interrupt or sleeping |
| `PulseAwakeThresholdMs` | 8 000 ms (8 s) | If gap since last pulse wake > this → isolated single pulse, sleep immediately; else → burst |
| `PulseAwakeQuietMs` | 30 000 ms (30 s) | No new pulses for this long → burst is over, exit awake counting |
| `PulseAwakeMaxMs` | 300 000 ms (5 min) | Hard cap on awake counting session |
| `AwakePulseFlushMs` | 5 000 ms (5 s) | Rate-limit for flushing burst pulses to EEPROM while staying awake |
| `WifiReconnectIntervalMs` | 10 000 ms (10 s) | Rate-limit for WiFi reconnect checks |
