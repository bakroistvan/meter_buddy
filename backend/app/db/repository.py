from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.schemas import UploadPayload


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
              raw_json TEXT NOT NULL
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

            CREATE INDEX IF NOT EXISTS idx_meter_readings_device_timestamp
              ON meter_readings(device_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_meter_readings_dump_id
              ON meter_readings(dump_id);
            """
        )


def store_upload(payload: UploadPayload) -> tuple[int, int]:
    received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    raw_json = json.dumps(payload.model_dump(mode="json"), separators=(",", ":"))

    with connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO upload_dumps (
              received_at,
              device_id,
              meter_impulses_per_kwh,
              upload_trigger,
              reading_count,
              raw_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                received_at,
                payload.device_id,
                payload.meter_impulses_per_kwh,
                payload.upload_trigger,
                len(payload.readings),
                raw_json,
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
                    reading.timestamp.isoformat().replace("+00:00", "Z"),
                    reading.period_start.isoformat().replace("+00:00", "Z")
                    if reading.period_start
                    else None,
                    reading.pulses,
                    reading.battery_v,
                    reading.battery_pct_est,
                )
                for reading in payload.readings
            ],
        )

    return dump_id, len(payload.readings)


def list_dumps() -> list[sqlite3.Row]:
    with connection() as conn:
        return list(
            conn.execute(
                """
                SELECT
                  d.id,
                  d.received_at,
                  d.device_id,
                  d.meter_impulses_per_kwh,
                  d.upload_trigger,
                  d.reading_count,
                  (SELECT r.battery_v FROM meter_readings r WHERE r.dump_id = d.id ORDER BY r.id DESC LIMIT 1) AS battery_v,
                  (SELECT r.battery_pct_est FROM meter_readings r WHERE r.dump_id = d.id ORDER BY r.id DESC LIMIT 1) AS battery_pct_est
                FROM upload_dumps d
                ORDER BY d.received_at DESC, d.id DESC
                """
            )
        )


def get_dump_meta(dump_id: int) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT
              d.id,
              d.received_at,
              d.device_id,
              d.meter_impulses_per_kwh,
              d.upload_trigger,
              d.reading_count,
              (SELECT r.battery_v FROM meter_readings r WHERE r.dump_id = d.id ORDER BY r.id DESC LIMIT 1) AS battery_v,
              (SELECT r.battery_pct_est FROM meter_readings r WHERE r.dump_id = d.id ORDER BY r.id DESC LIMIT 1) AS battery_pct_est
            FROM upload_dumps d WHERE d.id = ?
            """,
            (dump_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


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
