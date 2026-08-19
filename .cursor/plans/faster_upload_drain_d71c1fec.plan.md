---
name: Faster upload drain
overview: Implement the faster upload drain on feature branch feat/faster-upload-drain (not main). Same JSON contract; remove upload-path hexdumps, compact LittleFS once per session, 128-record batches, HTTP keep-alive, and a cheaper JSON encoder.
todos:
  - id: feature-branch
    content: Create and switch to feature branch feat/faster-upload-drain from current main
    status: completed
  - id: remove-upload-hexdump
    content: Remove pre/post-roll hexdumps from handleUploadWake; keep REPL/diagnostics dumps
    status: completed
  - id: compact-once-seek
    content: "markSyncedThrough: persist cursor only; compact once after session; loadUploadBatch seeks past synced prefix"
    status: completed
  - id: batch-128
    content: Raise MaxUploadRecords to 128 and bump JSON reserve
    status: completed
  - id: http-session-reuse
    content: "Session-scoped HTTP client: keep-alive, construct TLS only for https"
    status: completed
  - id: faster-json
    content: "buildBody: stack iso8601 + snprintf/numeric concat, same JSON contract"
    status: completed
  - id: update-sot-docs
    content: Spawn SoT subagent for fw_specification + api/upload.md
    status: completed
isProject: false
---

# Faster multi-batch upload drain

Work on a feature branch, not `main`. Repo is currently on `main` (ahead of `origin/main`). First implementation step: `git checkout -b feat/faster-upload-drain` from that HEAD so all code/doc edits stay isolated. Do not commit unless asked.

Keep the current wire format (ISO-8601 timestamps, per-reading battery). The ~21 s POST loop in the captured drain is ~42× 48-record POSTs plus a LittleFS rewrite after every ack, and the hexdump before Wi‑Fi is another tens of seconds.

```mermaid
flowchart LR
  branch[feat/faster-upload-drain] --> hex[Remove upload hexdumps]
  hex --> compact[Compact once per session]
  compact --> batch[Raise batch to 128]
  batch --> http[Reuse HTTP client]
  http --> json[Faster JSON encode]
```

## 0. Feature branch

You are on `main` (5 commits ahead of `origin/main`). Before any firmware/doc edits:

```text
git checkout -b feat/faster-upload-drain
```

All steps below happen on that branch. No commit/push unless you ask.

## 1. Stop dumping the whole filesystem on every upload

[`handleUploadWake`](src/main.cpp) always calls `storage::hexdump(Serial)` before and after `rollCurrentPeriod` (unconditional, not behind `EnableSerialLogs`). That is the dump in the captured log and dominates time *before* `wifi connect start`.

- Remove both upload-path hexdumps.
- Keep REPL `h` and diagnostics-boot dump.

## 2. Compact once; seek past the synced prefix

Today [`markSyncedThrough`](src/storage.cpp) writes `/sync.dat` then **rewrites all remaining `/records.bin`** after every HTTP 200/201. That is quadratic LittleFS I/O (and the ~1.6 s stalls).

- `markSyncedThrough`: advance `syncedThrough` + `saveSyncState()` only.
- After the upload loop in `handleUploadWake`, if any readings were acked (`uploadedRecords`), call `compactRecords()` once (including when a later batch fails).
- Empty heartbeat still does not compact.
- Boot [`repairSyncState`](src/storage.cpp) already compacts when `minSequence <= syncedThrough` (crash safety).

Without mid-loop compact, [`loadUploadBatch`](src/storage.cpp) would rescan the acked prefix every POST. After reading the first record, seek:

`offset = (syncedThrough - first.sequence + 1) * sizeof(ReadingRecord)` when `first.sequence <= syncedThrough` (dense 16-byte records; CRC failure still stops as today).

## 3. Raise `MaxUploadRecords` from 48 to 128

In [`include/storage.h`](include/storage.h): `constexpr uint8_t MaxUploadRecords = 128`.

- `UploadBatch::count` can stay `uint8_t`.
- Stack batch ≈ 2 KB; JSON ≈ 18 KB — OK on ESP32-C3 with Wi‑Fi/TLS.
- Same backlog: ~16 POSTs instead of ~42.
- Bump `buildBody` reserve (`count * 140`).

No backend schema change; the API already accepts a list of readings.

## 4. Reuse one HTTP client for the session

[`sendBatch`](src/upload.cpp) constructs **both** `WiFiClient` and `WiFiClientSecure` every POST, then `http.begin` / `POST` / `http.end()` (closes TCP). Spec already says POSTs reuse the connection; the code does not.

- Add a small session type in upload (owned by `handleUploadWake`): pick plain vs TLS once, `setReuse(true)`, `begin` once, POST each batch, `end` after the loop (before OTA, which uses a different URL).
- Do not construct `WiFiClientSecure` on `http://`.
- `dump` / `buildBody` stay independent of the session.
- Keep `ensureWifiConnected` as a cheap reconnect if the link drops.

## 5. Encode JSON without temporary `String`s

Same keys and values. In `buildBody`:

- `iso8601`: `strftime` into a stack buffer and `body += buf` (or append into `body` directly) — no returned `String`.
- Numeric fields: `body += record.pulses` / `snprintf` for `battery_v` (3 decimals), not `String(...)`.
- Leave ISO-8601 and per-reading battery as-is (API unchanged).

## Out of scope

- Unix timestamps / dropping per-reading battery (API + backend).
- Streaming chunked POST (little gain at ~18 KB).
- Changing NTP/Wi‑Fi connect (already once per wake).

## Docs (after code)

Normative updates via the usual SoT subagent:

- [`docs/firmware/fw_specification.md`](docs/firmware/fw_specification.md) — batch size 128; compact once after the session (still persist `/sync.dat` per acked batch); no hexdump on the upload path; HTTP keep-alive for the POST loop.
- [`docs/api/upload.md`](docs/api/upload.md) — “≤48 readings” → 128.
