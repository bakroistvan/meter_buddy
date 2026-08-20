# Firmware OTA API contract

Shared contract between ESP32 firmware (`upload::checkFirmwareUpdate` in `src/upload.cpp`, Arduino `HTTPUpdate`) and the backend firmware routes (`backend/app/api/routes_firmware.py`, mirror in `backend/app/services/firmware_mirror.py`).

**Important:** `config::FirmwareVersionUrl` is the **HTTPUpdate** endpoint (`GET …/firmware/version`). It is **not** a JSON version document. A successful “update available” response is an `application/octet-stream` `.bin` body (plus `x-MD5`), not JSON metadata.

Operator token / GitHub PAT setup: [backend/GITHUB_TOKEN.md](../../backend/GITHUB_TOKEN.md). Deploy notes: [backend/README.md](../../backend/README.md).

---

## Device endpoint (Arduino HTTPUpdate)

| Item | Value |
| --- | --- |
| Method | `GET` |
| Path | `/api/meter-buddy/firmware/version` |
| Auth | HTTP Basic (`METER_BUDDY_AUTH_USER` / `METER_BUDDY_AUTH_PASSWORD`) — same credentials as upload |
| Client header | `x-ESP32-version: <device semver>` (sent by `HTTPUpdate` from the version string passed to `update()`) |
| Success (current) | `304 Not Modified` — no body |
| Success (newer image) | `200 OK`, `Content-Type: application/octet-stream`, response header `x-MD5: <hex>`, body = mirrored `.bin` |
| Unavailable | `503 Service Unavailable` — empty mirror, invalid latest tag, or missing file on disk |

Firmware constructs `HTTPUpdate(OtaTimeoutMs)` (default **120000** ms) and passes a request callback that calls `HTTPClient::setAuthorization(BasicAuthUser, BasicAuthPassword)` (Arduino-ESP32 2.x API). TLS trust matches upload (`TlsCaCert` / `AllowInsecureTls`).

Reverse proxies in front of the backend should allow long downloads (Compose Caddy uses **120s** `read_timeout` / `write_timeout` on the reverse proxy).

### Semver comparison

Latest mirrored release is chosen from on-disk `manifest.json` (highest parseable semver). Tags like `v0.4.0` and device strings like `0.4.0` / `v0.4.0` parse the same major.minor.patch.

| Device `x-ESP32-version` | Outcome |
| --- | --- |
| Parseable and **≥** latest mirrored semver | `304` |
| Parseable and **&lt;** latest, and `.bin` present | `200` + `x-MD5` + body |
| Unparseable / empty | Treated as older → `200` once a valid mirrored image exists |
| Dummy parseable `1.0.0` while latest is still `0.x` | `304` (no update) — USB-flash once so the device reports an injected git tag |
| No mirrored release / bad tag / missing file | `503` |

### Device version string source

1. Prefer compile-time `FIRMWARE_VERSION` injected by [`script/pio_firmware_version.py`](../../script/pio_firmware_version.py) (`git describe --tags --always`, else `0.0.0-unknown`).
2. Else `config::FirmwareVersion` (example default `1.0.0`).

USB flash remains the primary install path; OTA runs after a successful upload that delivered readings (US-10) or when the operator triggers `o` / `o[ta]` in the diagnostics REPL (US-6) — see [fw_specification.md](../firmware/fw_specification.md).

---

## Mirror behavior (backend)

On startup the backend starts a background poller (`mirror.start_background_sync()`):

- Syncs **once immediately**, then every `METER_BUDDY_FIRMWARE_SYNC_INTERVAL_SEC` (default **86400**; minimum 60).
- Disabled when `METER_BUDDY_FIRMWARE_DISABLE_SYNC` is truthy (`1` / `true` / `yes`) — used in tests.
- Fetches GitHub Releases for `METER_BUDDY_GITHUB_REPO` (default `bakroistvan/meter_buddy`).
- Skips drafts and prereleases; requires a parseable semver tag.
- Mirrors application assets matching `meter-buddy-fw-v*.bin` (excludes `*-partitions.bin` and `.elf`).
- Writes binaries under `METER_BUDDY_FIRMWARE_DIR` (Docker default `/data/firmware`; local default `backend/data/firmware`) and updates `manifest.json` (tag, published_at, filename, size, md5).
- Optional `METER_BUDDY_GITHUB_TOKEN` (Bearer) for private/rate-limited API access — see [GITHUB_TOKEN.md](../../backend/GITHUB_TOKEN.md).

---

## Operator endpoints

All require the same HTTP Basic Auth as upload.

### `GET /api/meter-buddy/firmware`

JSON status of the local mirror (not used by the device):

| Field | Notes |
| --- | --- |
| `repo` | Configured GitHub repo |
| `firmware_dir` | Absolute mirror path |
| `sync_interval_sec` | Poll interval |
| `status` | `last_sync_at`, `last_error`, `last_ok` |
| `releases` | Mirrored entries (tag, published_at, filename, size, md5) |
| `latest` | Highest-semver entry or `null` |

### `POST /api/meter-buddy/firmware/sync`

Triggers an immediate GitHub → disk sync.

| Outcome | Response |
| --- | --- |
| Success | `200` JSON: `ok: true`, `synced` count, `releases`, `status` |
| Failure | `502 Bad Gateway` with `detail` from the sync error |

---

## Example curls

```bash
# Device-style check (expect 304 if already on latest)
curl -i -u 'meter-buddy:your-secret' \
  -H 'x-ESP32-version: 0.4.0' \
  'https://example.com/api/meter-buddy/firmware/version'

# Operator list
curl -u 'meter-buddy:your-secret' \
  'https://example.com/api/meter-buddy/firmware'

# Operator force sync
curl -i -X POST -u 'meter-buddy:your-secret' \
  'https://example.com/api/meter-buddy/firmware/sync'
```
