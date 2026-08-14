# Meter Buddy documentation

Agent entry point (basic knowledge + doc links): [../AGENT.md](../AGENT.md).

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
| [api/firmware.md](api/firmware.md) | Firmware ↔ backend OTA / HTTPUpdate contract + mirror operator routes |
| [hardware/schematic.md](hardware/schematic.md) | Module schematic, nets, BOM, EasyEDA import notes |
| [hardware/meter_buddy.netlist.json](hardware/meter_buddy.netlist.json) | EasyEDA Pro netlist-rebuild import |

Monorepo/backend layout formerly described in `architecture.md` is historical; current backend setup lives in [backend/README.md](../backend/README.md), [api/upload.md](api/upload.md), and [api/firmware.md](api/firmware.md). Hardware build detail beyond the fw_specification assumptions is also summarized in the [root README](../README.md) and [hardware/schematic.md](hardware/schematic.md).

## Package READMEs

- [Root README](../README.md) — hardware overview, firmware build/flash
- [Backend README](../backend/README.md) — API server setup, Docker, tests

## Archive

Non-normative historical docs under [archive/](archive/):

| File | Former role |
| --- | --- |
| [archive/intent.md](archive/intent.md) | Early design intent |
| [archive/architecture.md](archive/architecture.md) | Monorepo layout notes |
| [archive/wiring.md](archive/wiring.md) | Hardware wiring (superseded by fw_specification hardware section) |
| [archive/timing.md](archive/timing.md) | Timing notes (often stale) |
| [archive/input_flows.md](archive/input_flows.md) | Wake/input flow notes (often stale) |
| Other files in [archive/](archive/) | Older planning / status snapshots |
