from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.schemas import UploadPayload
from app.services.statistics import SparseReading


def default_db_path() -> Path:
    # app/db/repository.py → parents[2] == backend/
    return Path(__file__).resolve().parents[2] / "data" / "meter_buddy.sqlite3"


def db_path() -> Path:
    return Path(os.getenv("METER_BUDDY_DB_PATH", str(default_db_path())))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    typedef: str,
) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_db() -> None:
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS upload_dumps (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              received_at TEXT NOT NULL,
              device_id TEXT NOT NULL,
              meter_impulses_per_kwh INTEGER NOT NULL,
              upload_trigger TEXT,
              reading_count INTEGER NOT NULL,
              raw_json TEXT NOT NULL,
              upload_session_id TEXT,
              last_batch INTEGER
            );

            CREATE TABLE IF NOT EXISTS meter_readings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              dump_id INTEGER NOT NULL REFERENCES upload_dumps(id) ON DELETE CASCADE,
              device_id TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              period_start TEXT,
              pulses INTEGER NOT NULL,
              battery_v REAL,
              battery_pct_est INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_upload_dumps_received_at
              ON upload_dumps(received_at);

            CREATE INDEX IF NOT EXISTS idx_upload_dumps_device_id
              ON upload_dumps(device_id);

            CREATE INDEX IF NOT EXISTS idx_meter_readings_device_timestamp
              ON meter_readings(device_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_meter_readings_dump_id
              ON meter_readings(dump_id);
            """
        )
        # Existing DBs created before session columns: add if missing.
        _ensure_column(conn, "upload_dumps", "upload_session_id", "TEXT")
        _ensure_column(conn, "upload_dumps", "last_batch", "INTEGER")


def _iso_z(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _normalize_dump_meta(row: sqlite3.Row | dict) -> dict:
    meta = dict(row)
    last_batch = meta.get("last_batch")
    if last_batch is None:
        meta["last_batch"] = None
    else:
        meta["last_batch"] = bool(last_batch)
    return meta


_DUMP_META_SELECT = """
    SELECT
      d.id,
      d.received_at,
      d.device_id,
      d.meter_impulses_per_kwh,
      d.upload_trigger,
      d.reading_count,
      COALESCE(
        d.upload_session_id,
        json_extract(d.raw_json, '$.upload_session_id')
      ) AS upload_session_id,
      COALESCE(
        d.last_batch,
        json_extract(d.raw_json, '$.last_batch')
      ) AS last_batch,
      json_extract(d.raw_json, '$.battery_v') AS battery_v,
      json_extract(d.raw_json, '$.battery_pct_est') AS battery_pct_est
    FROM upload_dumps d
"""


def store_upload(payload: UploadPayload) -> tuple[int, int]:
    received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    raw_json = json.dumps(
        payload.model_dump(mode="json", exclude_none=True), separators=(",", ":")
    )
    last_batch_db: int | None
    if payload.last_batch is None:
        last_batch_db = None
    else:
        last_batch_db = 1 if payload.last_batch else 0

    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO upload_dumps (
              received_at,
              device_id,
              meter_impulses_per_kwh,
              upload_trigger,
              reading_count,
              raw_json,
              upload_session_id,
              last_batch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                received_at,
                payload.device_id,
                payload.meter_impulses_per_kwh,
                payload.upload_trigger,
                len(payload.readings),
                raw_json,
                payload.upload_session_id,
                last_batch_db,
            ),
        )
        dump_id = int(cursor.lastrowid)

        conn.executemany(
            """
            INSERT INTO meter_readings (
              dump_id,
              device_id,
              timestamp,
              period_start,
              pulses,
              battery_v,
              battery_pct_est
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    dump_id,
                    payload.device_id,
                    _iso_z(reading.timestamp),
                    _iso_z(reading.period_start) if reading.period_start else None,
                    reading.pulses,
                    reading.battery_v,
                    reading.battery_pct_est,
                )
                for reading in payload.readings
            ],
        )

    return dump_id, len(payload.readings)


def list_dumps() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            f"""
            {_DUMP_META_SELECT}
            ORDER BY d.received_at DESC, d.id DESC
            """
        ).fetchall()
    return [_normalize_dump_meta(row) for row in rows]


def get_dump_meta(dump_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            f"""
            {_DUMP_META_SELECT}
            WHERE d.id = ?
            """,
            (dump_id,),
        ).fetchone()
    if row is None:
        return None
    return _normalize_dump_meta(row)


def get_dump_json(dump_id: int) -> str | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT raw_json FROM upload_dumps WHERE id = ?",
            (dump_id,),
        ).fetchone()
    if row is None:
        return None
    return str(row["raw_json"])


def delete_dump(dump_id: int) -> bool:
    with connection() as conn:
        cursor = conn.execute(
            "DELETE FROM upload_dumps WHERE id = ?",
            (dump_id,),
        )
        return cursor.rowcount > 0


def delete_dumps_up_to(max_id: int) -> int:
    with connection() as conn:
        cursor = conn.execute(
            "DELETE FROM upload_dumps WHERE id <= ?",
            (max_id,),
        )
        return int(cursor.rowcount)


def reset_db() -> None:
    path = db_path()
    if path.exists():
        path.unlink()
    init_db()


def replace_db_file(content: bytes) -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_bytes(content)

    conn = None
    try:
        conn = sqlite3.connect(temp_path)
        conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    except Exception as e:
        if conn:
            conn.close()
        if temp_path.exists():
            temp_path.unlink()
        raise ValueError(f"Invalid SQLite database file: {e}") from e
    else:
        conn.close()

    if path.exists():
        path.unlink()
    temp_path.replace(path)
    init_db()


def device_exists(device_id: str) -> bool:
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM upload_dumps WHERE device_id = ? LIMIT 1",
            (device_id,),
        ).fetchone()
    return row is not None


def list_devices() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT
              d.device_id AS device_id,
              MAX(d.received_at) AS last_seen,
              (
                SELECT COUNT(*)
                FROM meter_readings mr
                WHERE mr.device_id = d.device_id
              ) AS reading_count
            FROM upload_dumps d
            GROUP BY d.device_id
            ORDER BY last_seen DESC, d.device_id ASC
            """
        ).fetchall()
    return [
        {
            "device_id": row["device_id"],
            "last_seen": row["last_seen"],
            "reading_count": int(row["reading_count"]),
        }
        for row in rows
    ]


def list_device_sparse_readings(
    device_id: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[SparseReading]:
    clauses = ["r.device_id = ?"]
    params: list[object] = [device_id]
    if since is not None:
        clauses.append("r.timestamp >= ?")
        params.append(_iso_z(_ensure_utc(since)))
    if until is not None:
        clauses.append("r.timestamp < ?")
        params.append(_iso_z(_ensure_utc(until)))
    where = " AND ".join(clauses)

    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
              r.timestamp,
              r.period_start,
              r.pulses,
              d.meter_impulses_per_kwh
            FROM meter_readings r
            JOIN upload_dumps d ON d.id = r.dump_id
            WHERE {where}
            ORDER BY r.timestamp ASC, r.id ASC
            """,
            params,
        ).fetchall()

    out: list[SparseReading] = []
    for row in rows:
        ts = _parse_iso(str(row["timestamp"]))
        if ts is None:
            continue
        out.append(
            SparseReading(
                timestamp=ts,
                period_start=_parse_iso(row["period_start"]),
                pulses=int(row["pulses"]),
                impulses_per_kwh=int(row["meter_impulses_per_kwh"]),
            )
        )
    return out


def list_device_readings_debug(
    device_id: str,
    *,
    since: datetime | None = None,
) -> list[dict]:
    clauses = ["r.device_id = ?"]
    params: list[object] = [device_id]
    if since is not None:
        clauses.append("r.timestamp >= ?")
        params.append(_iso_z(_ensure_utc(since)))
    where = " AND ".join(clauses)

    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
              r.id,
              r.dump_id,
              r.timestamp,
              r.period_start,
              r.pulses,
              r.battery_v,
              r.battery_pct_est,
              d.meter_impulses_per_kwh
            FROM meter_readings r
            JOIN upload_dumps d ON d.id = r.dump_id
            WHERE {where}
            ORDER BY r.timestamp ASC, r.id ASC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_device_state_row(device_id: str) -> dict | None:
    """Latest dump + last reading fields for live state."""
    with connection() as conn:
        dump = conn.execute(
            """
            SELECT
              device_id,
              meter_impulses_per_kwh,
              json_extract(raw_json, '$.battery_v') AS dump_battery_v,
              json_extract(raw_json, '$.battery_pct_est') AS dump_battery_pct_est
            FROM upload_dumps
            WHERE device_id = ?
            ORDER BY received_at DESC, id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        if dump is None:
            return None

        last_reading = conn.execute(
            """
            SELECT
              timestamp,
              period_start,
              pulses,
              battery_v,
              battery_pct_est
            FROM meter_readings
            WHERE device_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()

    result = {
        "device_id": dump["device_id"],
        "meter_impulses_per_kwh": int(dump["meter_impulses_per_kwh"]),
        "battery_v": dump["dump_battery_v"],
        "battery_pct_est": dump["dump_battery_pct_est"],
        "last_timestamp": None,
        "last_period_start": None,
        "last_pulses": None,
    }
    if last_reading is not None:
        result["last_timestamp"] = last_reading["timestamp"]
        result["last_period_start"] = last_reading["period_start"]
        result["last_pulses"] = int(last_reading["pulses"])
        if last_reading["battery_v"] is not None:
            result["battery_v"] = last_reading["battery_v"]
        if last_reading["battery_pct_est"] is not None:
            result["battery_pct_est"] = last_reading["battery_pct_est"]
    return result


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)
