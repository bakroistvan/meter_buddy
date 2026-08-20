# Meter Buddy documentation

Documentation index and production configuration guide for field deployments.

## Production firmware config

Compile-time settings live in [`include/config.example.h`](../include/config.example.h). For a real device, copy it to gitignored [`include/local_config.h`](../include/local_config.h) and override values in the same `config` namespace.

### Required per device

| Setting | Notes |
| --- | --- |
| `DeviceId` | Unique id in every upload JSON |
| `WifiSsid` / `WifiPassword` | Hotspot or AP used only during upload |
| `UploadUrl` | HTTPS endpoint (must match backend `/api/meter-buddy/upload`) |
| `BasicAuthUser` / `BasicAuthPassword` | Must match backend `METER_BUDDY_AUTH_*` |
| `MeterImpulsesPerKwh` | Must match the meter S0 constant |

### Recommended production knobs

| Setting | Production value | Why |
| --- | --- | --- |
| `EnableDeepSleep` | `true` | Battery life |
| `StayAwakeBoot` | `false` | No diagnostics REPL on battery boot |
| `AllowInsecureTls` | `false` | Verified HTTPS only |
| `KeepWifiConnectedWhenAwake` | `false` | Radio off between uploads |
| `EnableSerialLogs` | `false` | Less UART activity and power draw |
| `LedEventMask` | `Awake \| RtcRoll \| Pulse` | Suppress routine indicators (default in example) |

`TlsCaCert` defaults to vendored Let's Encrypt ISRG roots (`certs/isrg_roots.h`); leave as-is unless pinning a different CA.

### LED event mask

Routine wake/housekeeping LEDs draw power on every pulse and RTC period. Mask them in production; user-action feedback stays visible.

Defaults live in [`include/led_events.h`](../include/led_events.h) (always included from `config.h`). Production default masks all three routine events.

```cpp
namespace config::led_event {
constexpr uint8_t Awake   = 1 << 0; // dim status LED while idle-awake
constexpr uint8_t RtcRoll = 1 << 1; // status blink on period roll
constexpr uint8_t Pulse   = 1 << 2; // D8 flash per accepted pulse
}

// Bits set in LedEventMask = suppressed
constexpr uint8_t LedEventMask =
    led_event::Awake | led_event::RtcRoll | led_event::Pulse;
```

For bench bring-up, add at the top of `local_config.h` before the namespace:

```cpp
#define METER_BUDDY_LED_EVENT_MASK 0
```

| Mask bit | When unmasked (bench) | When masked (production default) |
| --- | --- | --- |
| `Awake` | Dim PWM on D10 while awake | LED stays off between user actions |
| `RtcRoll` | One status blink on RTC period roll | No blink on housekeeping |
| `Pulse` | ~100 ms flash on D8 per pulse | No pulse LED activity |

**Still shown** (never masked): upload in progress (`startPulseBlink`), upload failure / protection block (`rapidErrorBlink`), stay-awake toggle (`setOn` + `doubleBlink`).

Full LED semantics: [firmware/fw_specification.md](firmware/fw_specification.md) (US-8).

### Backend

Production server setup: [backend/README.md](../backend/README.md). Upload wire contract: [api/upload.md](api/upload.md).

---

## Single source of truth

| Doc | Description |
| --- | --- |
| [intent_spec.md](intent_spec.md) | User requirements (no implementation choices) |
| [firmware/fw_specification.md](firmware/fw_specification.md) | Firmware behavior (user stories, architecture, wake/interrupt flows, hardware assumptions) |

These two documents are normative for product requirements and firmware behavior. Prefer them over archived notes.

## Other living docs

| Doc | Description |
| --- | --- |
| [api/upload.md](api/upload.md) | Firmware ↔ backend upload contract |
| [hardware/schematic.md](hardware/schematic.md) | Module schematic, nets, BOM, EasyEDA import notes |
| [hardware/meter_buddy.netlist.json](hardware/meter_buddy.netlist.json) | EasyEDA Pro netlist-rebuild import |

Monorepo/backend layout formerly described in `architecture.md` is historical; current backend setup lives in [backend/README.md](../backend/README.md) and [api/upload.md](api/upload.md). Hardware build detail beyond the fw_specification assumptions is also summarized in the [root README](../README.md) and [hardware/schematic.md](hardware/schematic.md).

## Package READMEs

- [Root README](../README.md) — hardware overview, firmware build/flash
- [Backend README](../backend/README.md) — API server setup, Docker, tests

## Archive

Non-normative historical docs under [archive/](archive/): early intent, wiring, timing, and planning snapshots. Do not treat as current behavior.

## For agents

Agent entry point: [../AGENT.md](../AGENT.md).
