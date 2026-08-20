# Meter Buddy (Home Assistant)

HACS custom integration that pulls live power/energy and historical statistics from the Meter Buddy backend. The device never talks to Home Assistant; HA listens on the backend WebSocket and imports after each upload **session** completes.

Wire contract: [docs/api/upload.md](../../docs/api/upload.md). Product requirements: [docs/intent_spec.md](../../docs/intent_spec.md) (P-9, N-1, N-6).

## Requirements

- Home Assistant **2024.1.0+** (`hacs.json`)
- Reachable Meter Buddy backend with Basic Auth
- At least one prior device upload (so `GET /api/devices` is non-empty)

## Install

### Option A — HACS (recommended)

1. In Home Assistant open **HACS** → menu (⋮) → **Custom repositories**.
2. Paste the **GitHub repository URL** (not this README path, not a release zip):
   - `https://github.com/bakroistvan/meter_buddy`
   - Category: **Integration**
3. Click **Add**. HACS looks for root `hacs.json` and `custom_components/meter_buddy/` in that repo.
4. Find **Meter Buddy** under HACS → Integrations → **Download** (or **Explore & Download Repositories**).
5. **Branch selection (important):** the custom-repository dialog only accepts the **repo URL** — you cannot paste `…/tree/feature/hass-energy-integration` there. Until this lands on `main` / a release:
   1. Download whatever HACS offers first (often the default branch), **or** skip straight to the action below if the integration is not on `main` yet.
   2. Developer tools → **Actions** → call **`update.install`**.
   3. Choose the Meter Buddy update entity (name like `update.meter_buddy_update`).
   4. Set **version** to the exact branch name: `feature/hass-energy-integration` (or a commit SHA).
   5. Run the action, then restart Home Assistant.
6. Settings → Devices & services → **Add Integration** → **Meter Buddy**.
7. Enter:
   - **Base URL** — backend origin only (e.g. `https://meter-buddy.example.com`), no path; `http`/`https` required
   - **Username** / **Password** — same Basic Auth as the backend (`METER_BUDDY_AUTH_*`)
8. Pick a `device_id` from the list returned by `GET /api/devices`.
9. One config entry per `device_id` (unique id = `device_id`).

The branch must be **pushed to GitHub** before HACS can fetch it. If `update.install` is awkward, use **Option B** and copy from a local checkout of `feature/hass-energy-integration`.

Repo root `hacs.json` sets `"render_readme": true` so HACS shows this README.

### Option B — manual copy

1. Check out the branch that has the integration (`feature/hass-energy-integration`), then copy `custom_components/meter_buddy` into Home Assistant’s `/config/custom_components/meter_buddy` (create `custom_components` if missing).
2. Restart Home Assistant, then continue from **Add Integration** as in Option A steps 6–9.

## Config flow behavior

| Step | What happens |
| --- | --- |
| User | Validates base URL; `GET /api/devices` with Basic Auth. Errors: `invalid_url`, `invalid_auth`, `cannot_connect`, `no_devices` |
| Device | Dropdown of `device_id` values; creates entry titled `Meter Buddy ({device_id})` with `import_schema` default `1` |

Stored entry data: `base_url`, `username`, `password`, `device_id`, `import_schema`, and later a `watermark` (latest imported bucket start) updated after each successful statistics import.

## Entities

Entity object ids use a slugified `device_id` (non-alnum → `_`), e.g. `meter-buddy-001` → `meter_buddy_001`.

| Sensor | Unit | State class | Notes |
| --- | --- | --- | --- |
| Power | W | `measurement` | Last period power from `/state` (`power_w`; `0` when unknown) |
| Energy | kWh | `total_increasing` | Absolute backend lifetime total from `/state` (`energy_kwh`) — never previous + delta |
| Battery | % | — | Only created when `battery_pct_est` is present on `/state`; added later if battery appears after setup |

Device info: manufacturer Meter Buddy, model Logger, identifier `(meter_buddy, device_id)`.

## Energy dashboard

1. Settings → Dashboards → Energy → Electricity grid → Add consumption.
2. Select the **Energy** sensor (`sensor.meter_buddy_<slug>_energy`).
3. Do **not** add a Riemann sum helper on Power — long-term Energy history comes from recorder statistics imported after each upload session.

## When statistics are imported (wait for `last_batch`)

Upload wakes may POST many batches of up to **128** readings. HA must not import mid-session.

| Trigger | Behavior |
| --- | --- |
| First setup | Immediate full import: `GET …/statistics` (hour + 5min, no watermark) + `GET …/state`; push into recorder via `async_import_statistics` |
| WebSocket `new_dump` with `last_batch: false` | Record session id; **wait** (do not import); restart **60 s** timeout (`SESSION_COMPLETE_TIMEOUT_SECONDS`) |
| WebSocket `new_dump` with `last_batch: true` (or missing/`null` treated as complete) | Cancel timeout; one import under a lock |
| 60 s timeout while waiting | Import whatever the backend already has for that session |
| Other devices’ dumps | Ignored |
| 10-minute poll | Fallback snapshot import (`DEFAULT_SCAN_INTERVAL_SECONDS = 600`) |

Each import:

1. `GET /api/devices/{id}/statistics?bucket=hour` and `bucket=5min` (optional `since=` watermark after the first full import).
2. `GET /api/devices/{id}/state`.
3. Map buckets to HA statistics rows (`sum` = cumulative `energy_kwh_sum` for energy; mean power for power) and call `async_import_statistics` for both entities.
4. Set live sensor values; advance watermark to the latest bucket `start`.

Live energy always overwrites from `/state.energy_kwh` (absolute), matching `session.apply_absolute_energy`.

## Development / tests

Unit tests under `custom_components/meter_buddy/tests/` (coordinator session wait, statistics mapper). End-to-end backend path that exercises generator → upload → `/statistics` → HA mapper stub: [backend/tests/test_sim_ha_catchup.py](../../backend/tests/test_sim_ha_catchup.py). Catch-up payload generator: [tools/ha_catchup/README.md](../../tools/ha_catchup/README.md).
