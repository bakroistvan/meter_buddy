"""Pure generators for firmware-like sparse upload batches (no network)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any

DEFAULT_BATTERY_V = 3.775
DEFAULT_BATTERY_PCT = 50
MAX_UPLOAD_RECORDS = 128


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return _ensure_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_sparse_readings(
    start: datetime,
    end: datetime,
    *,
    impulses_per_kwh: int = 1000,
    pulse_probability: float = 0.3,
    pulses_when_active: int = 10,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Build sparse 1-minute readings; omit minutes with zero pulses.

    ``impulses_per_kwh`` is accepted for call-site symmetry with chunking; readings
    do not embed it (it belongs on the upload batch).
    """
    if impulses_per_kwh <= 0:
        raise ValueError("impulses_per_kwh must be positive")
    if not 0.0 <= pulse_probability <= 1.0:
        raise ValueError("pulse_probability must be in [0, 1]")
    if pulses_when_active < 0:
        raise ValueError("pulses_when_active must be >= 0")

    start_utc = _ensure_utc(start)
    end_utc = _ensure_utc(end)
    if end_utc <= start_utc:
        return []

    rng = Random(seed)
    period = timedelta(minutes=1)
    readings: list[dict[str, Any]] = []
    cursor = start_utc

    while cursor < end_utc:
        period_end = cursor + period
        if period_end > end_utc:
            break
        if rng.random() < pulse_probability:
            readings.append(
                {
                    "timestamp": _iso_z(period_end),
                    "period_start": _iso_z(cursor),
                    "pulses": pulses_when_active,
                    "battery_v": DEFAULT_BATTERY_V,
                    "battery_pct_est": DEFAULT_BATTERY_PCT,
                }
            )
        cursor = period_end

    return readings


def chunk_upload_batches(
    readings: list[dict],
    *,
    device_id: str = "meter-buddy-001",
    impulses_per_kwh: int = 1000,
    session_id: str | None = None,
    max_records: int = MAX_UPLOAD_RECORDS,
) -> list[dict[str, Any]]:
    """Chunk sparse readings into upload POST bodies (MaxUploadRecords-sized).

    Empty ``readings`` yields a single heartbeat with ``last_batch`` true.
    Top-level battery keys appear only on the first batch.
    """
    if max_records < 1:
        raise ValueError("max_records must be >= 1")
    if impulses_per_kwh <= 0:
        raise ValueError("impulses_per_kwh must be positive")

    upload_session_id = session_id if session_id is not None else uuid.uuid4().hex

    if not readings:
        return [
            {
                "device_id": device_id,
                "meter_impulses_per_kwh": impulses_per_kwh,
                "upload_trigger": "button",
                "upload_session_id": upload_session_id,
                "last_batch": True,
                "battery_v": DEFAULT_BATTERY_V,
                "battery_pct_est": DEFAULT_BATTERY_PCT,
                "readings": [],
            }
        ]

    batches: list[dict[str, Any]] = []
    total = len(readings)
    for offset in range(0, total, max_records):
        chunk = readings[offset : offset + max_records]
        is_first = offset == 0
        is_last = offset + max_records >= total
        body: dict[str, Any] = {
            "device_id": device_id,
            "meter_impulses_per_kwh": impulses_per_kwh,
            "upload_trigger": "button",
            "upload_session_id": upload_session_id,
            "last_batch": is_last,
            "readings": chunk,
        }
        if is_first:
            body["battery_v"] = DEFAULT_BATTERY_V
            body["battery_pct_est"] = DEFAULT_BATTERY_PCT
        batches.append(body)

    return batches
