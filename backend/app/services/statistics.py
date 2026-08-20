from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

BucketSize = Literal["hour", "5min"]

DEFAULT_PERIOD_SECONDS = 60.0


@dataclass(frozen=True)
class SparseReading:
    timestamp: datetime
    period_start: datetime | None
    pulses: int
    impulses_per_kwh: int


@dataclass(frozen=True)
class StatBucket:
    start: datetime
    energy_kwh_sum: float
    power_w_mean: float


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def period_dt_seconds(
    timestamp: datetime,
    period_start: datetime | None,
    default: float = DEFAULT_PERIOD_SECONDS,
) -> float:
    if period_start is not None:
        start = _as_utc(period_start)
        end = _as_utc(timestamp)
        dt = (end - start).total_seconds()
        if dt > 0:
            return dt
    return float(default)


def reading_energy_kwh(pulses: int, impulses_per_kwh: int) -> float:
    return pulses / impulses_per_kwh


def reading_power_w(
    pulses: int,
    impulses_per_kwh: int,
    dt_s: float,
) -> float:
    if dt_s <= 0:
        dt_s = DEFAULT_PERIOD_SECONDS
    return (pulses / impulses_per_kwh) / (dt_s / 3600.0) * 1000.0


def bucket_start(ts: datetime, bucket: BucketSize) -> datetime:
    ts = _as_utc(ts).replace(second=0, microsecond=0)
    if bucket == "hour":
        return ts.replace(minute=0)
    minute = (ts.minute // 5) * 5
    return ts.replace(minute=minute)


def next_bucket(start: datetime, bucket: BucketSize) -> datetime:
    if bucket == "hour":
        return start + timedelta(hours=1)
    return start + timedelta(minutes=5)


def reading_bucket(reading: SparseReading, bucket: BucketSize) -> datetime:
    anchor = reading.period_start if reading.period_start is not None else reading.timestamp
    return bucket_start(anchor, bucket)


def aggregate_statistics(
    readings: list[SparseReading],
    *,
    bucket: BucketSize,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[StatBucket]:
    """Build 0-filled buckets from sparse pulse periods.

    - No buckets before the first stored period.
    - Idle buckets between first and last have power_w_mean=0 and carry energy.
    - energy_kwh_sum is lifetime cumulative kWh at bucket end (absolute).
    - since/until filter on bucket start (start >= since, start < until).
    """
    if not readings:
        return []

    ordered = sorted(readings, key=lambda r: (_as_utc(r.timestamp), r.pulses))
    bucket_powers: dict[datetime, list[float]] = {}
    bucket_energy: dict[datetime, float] = {}

    for reading in ordered:
        if reading.impulses_per_kwh <= 0:
            continue
        b_start = reading_bucket(reading, bucket)
        dt_s = period_dt_seconds(reading.timestamp, reading.period_start)
        energy = reading_energy_kwh(reading.pulses, reading.impulses_per_kwh)
        power = reading_power_w(reading.pulses, reading.impulses_per_kwh, dt_s)
        bucket_powers.setdefault(b_start, []).append(power)
        bucket_energy[b_start] = bucket_energy.get(b_start, 0.0) + energy

    if not bucket_energy:
        return []

    first_b = min(bucket_energy)
    last_b = max(bucket_energy)
    since_utc = _as_utc(since) if since is not None else None
    until_utc = _as_utc(until) if until is not None else None

    results: list[StatBucket] = []
    cumulative = 0.0
    current = first_b
    while current <= last_b:
        cumulative += bucket_energy.get(current, 0.0)
        include = True
        if since_utc is not None and current < since_utc:
            include = False
        if until_utc is not None and current >= until_utc:
            include = False
        if include:
            powers = bucket_powers.get(current, [])
            power_mean = sum(powers) / len(powers) if powers else 0.0
            results.append(
                StatBucket(
                    start=current,
                    energy_kwh_sum=cumulative,
                    power_w_mean=power_mean,
                )
            )
        current = next_bucket(current, bucket)

    return results


def total_energy_kwh(readings: list[SparseReading]) -> float:
    return sum(
        reading_energy_kwh(r.pulses, r.impulses_per_kwh)
        for r in readings
        if r.impulses_per_kwh > 0
    )


def last_period_power_w(readings: list[SparseReading]) -> float | None:
    if not readings:
        return None
    last = max(readings, key=lambda r: _as_utc(r.timestamp))
    if last.impulses_per_kwh <= 0:
        return None
    dt_s = period_dt_seconds(last.timestamp, last.period_start)
    return reading_power_w(last.pulses, last.impulses_per_kwh, dt_s)
