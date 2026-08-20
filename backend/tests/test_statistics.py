from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.statistics import SparseReading, aggregate_statistics


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _reading(
    timestamp: str,
    pulses: int,
    *,
    period_start: str | None = None,
    c: int = 1000,
) -> SparseReading:
    end = _ts(timestamp)
    start = _ts(period_start) if period_start else end - timedelta(seconds=60)
    return SparseReading(
        timestamp=end,
        period_start=start,
        pulses=pulses,
        impulses_per_kwh=c,
    )


def test_gaps_are_zero_power_with_carry_forward_energy():
    # Hour 10: 1000 pulses over 1h → 1.0 kWh, 1000 W
    # Hour 11: idle
    # Hour 12: 500 pulses over 1h → +0.5 kWh, 500 W
    readings = [
        _reading("2026-05-01T11:00:00Z", 1000, period_start="2026-05-01T10:00:00Z"),
        _reading("2026-05-01T13:00:00Z", 500, period_start="2026-05-01T12:00:00Z"),
    ]

    buckets = aggregate_statistics(readings, bucket="hour")
    assert [b.start.isoformat().replace("+00:00", "Z") for b in buckets] == [
        "2026-05-01T10:00:00Z",
        "2026-05-01T11:00:00Z",
        "2026-05-01T12:00:00Z",
    ]
    assert buckets[0].energy_kwh_sum == 1.0
    assert buckets[0].power_w_mean == 1000.0
    assert buckets[1].energy_kwh_sum == 1.0
    assert buckets[1].power_w_mean == 0.0
    assert buckets[2].energy_kwh_sum == 1.5
    assert buckets[2].power_w_mean == 500.0


def test_no_fill_before_first_period():
    readings = [
        _reading("2026-05-01T14:01:00Z", 100, period_start="2026-05-01T14:00:00Z"),
        _reading("2026-05-01T14:06:00Z", 100, period_start="2026-05-01T14:05:00Z"),
    ]
    buckets = aggregate_statistics(readings, bucket="5min")
    starts = [b.start for b in buckets]
    assert starts[0] == _ts("2026-05-01T14:00:00Z")
    assert all(s >= starts[0] for s in starts)
    # No 13:55 bucket
    assert _ts("2026-05-01T13:55:00Z") not in starts


def test_since_cursor_keeps_lifetime_cumulative():
    readings = [
        _reading("2026-05-01T10:01:00Z", 1000, period_start="2026-05-01T10:00:00Z"),
        _reading("2026-05-01T11:01:00Z", 1000, period_start="2026-05-01T11:00:00Z"),
        _reading("2026-05-01T12:01:00Z", 1000, period_start="2026-05-01T12:00:00Z"),
    ]
    since = _ts("2026-05-01T11:00:00Z")
    buckets = aggregate_statistics(readings, bucket="hour", since=since)
    assert [b.start.isoformat().replace("+00:00", "Z") for b in buckets] == [
        "2026-05-01T11:00:00Z",
        "2026-05-01T12:00:00Z",
    ]
    # Lifetime includes hour 10 energy even though that bucket is omitted.
    assert buckets[0].energy_kwh_sum == 2.0
    assert buckets[1].energy_kwh_sum == 3.0


def test_until_excludes_later_buckets():
    readings = [
        _reading("2026-05-01T10:01:00Z", 1000, period_start="2026-05-01T10:00:00Z"),
        _reading("2026-05-01T11:01:00Z", 1000, period_start="2026-05-01T11:00:00Z"),
        _reading("2026-05-01T12:01:00Z", 1000, period_start="2026-05-01T12:00:00Z"),
    ]
    buckets = aggregate_statistics(
        readings,
        bucket="hour",
        until=_ts("2026-05-01T12:00:00Z"),
    )
    assert [b.start.isoformat().replace("+00:00", "Z") for b in buckets] == [
        "2026-05-01T10:00:00Z",
        "2026-05-01T11:00:00Z",
    ]
    assert buckets[-1].energy_kwh_sum == 2.0


def test_empty_readings_yield_no_buckets():
    assert aggregate_statistics([], bucket="hour") == []


def test_default_period_dt_when_period_start_missing():
    reading = SparseReading(
        timestamp=_ts("2026-05-01T10:00:00Z"),
        period_start=None,
        pulses=1000,
        impulses_per_kwh=1000,
    )
    buckets = aggregate_statistics([reading], bucket="hour")
    assert len(buckets) == 1
    # 1 kWh over default 60s → 1000 * 60 = 60000 W? Wait:
    # (1 kWh) / (60/3600) * 1000 = 1 / 0.01666... * 1000 = 60 * 1000 = 60000 W
    assert buckets[0].power_w_mean == 60000.0
    assert buckets[0].energy_kwh_sum == 1.0
