# HA catch-up payload generator

Pure (no-network) helpers that build firmware-like sparse upload JSON batches for Home Assistant catch-up / backend sims. Used by unit tests and the e2e TestClient path.

## What it generates

- **Sparse 1-minute readings** — minutes with zero pulses are omitted (same sparsity shape as rolled LittleFS records with activity only).
- **Chunked upload bodies** — at most **128** readings per POST (`MAX_UPLOAD_RECORDS`), one shared `upload_session_id`, `last_batch: true` only on the final chunk (or on a single empty heartbeat).
- Top-level `battery_v` / `battery_pct_est` only on the **first** batch (defaults `3.775` V / `50%`).

API surface (`tools.ha_catchup`):

| Function | Role |
| --- | --- |
| `generate_sparse_readings(start, end, …)` | List of reading dicts (`timestamp`, `period_start`, `pulses`, battery keys) |
| `chunk_upload_batches(readings, …)` | List of full upload POST bodies ready for `POST /api/meter-buddy/upload` |

## CLI

From the repo root (Python 3.11+):

```bash
python -m tools.ha_catchup \
  --start 2026-05-01T00:00:00Z \
  --end 2026-05-01T06:00:00Z \
  --pulse-probability 0.4 \
  --pulses-when-active 10 \
  --impulses-per-kwh 1000 \
  --device-id meter-buddy-001 \
  --seed 42
```

Prints a JSON array of upload bodies to stdout. Useful flags:

| Flag | Default | Notes |
| --- | --- | --- |
| `--start` / `--end` | required | UTC ISO-8601 (`Z` or offset) |
| `--pulse-probability` | `0.3` | Chance a minute has pulses |
| `--pulses-when-active` | `10` | Pulse count when active |
| `--session-id` | random UUID hex | Fixed id for reproducible multi-batch sessions |
| `--max-records` | `128` | Chunk size (firmware `MaxUploadRecords`) |

## Pytest

Generator-only tests (chunking / `last_batch` flags):

```bash
pytest tools/ha_catchup/test_generate.py -q
```

## E2E sim path

Full pipeline (generator → multi-POST upload → WS `last_batch` → `/state` + `/statistics` → HA statistics mapper stub):

```bash
cd backend
pytest tests/test_sim_ha_catchup.py -q
```

See [backend/tests/test_sim_ha_catchup.py](../../backend/tests/test_sim_ha_catchup.py). Contract details: [docs/api/upload.md](../../docs/api/upload.md).
