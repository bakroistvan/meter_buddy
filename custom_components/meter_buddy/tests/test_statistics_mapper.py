"""Unit tests for backend → HA statistics mapper."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.meter_buddy.statistics import (
    MEAN_TYPE_ARITHMETIC,
    MEAN_TYPE_NONE,
    absolute_energy_kwh,
    is_five_min_aligned,
    is_hour_aligned,
    map_energy_statistics,
    map_power_statistics,
    parse_bucket_start,
)


def test_parse_bucket_start_iso_z() -> None:
    start = parse_bucket_start("2024-07-01T12:00:00Z")
    assert start == datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc)


def test_map_energy_statistics_absolute_sum_and_past_starts() -> None:
    buckets = [
        {"start": "2024-07-01T00:00:00Z", "energy_kwh_sum": 10.5, "power_w_mean": 100.0},
        {"start": "2024-07-01T01:00:00Z", "energy_kwh_sum": 11.0, "power_w_mean": 0.0},
    ]
    meta, stats = map_energy_statistics("sensor.meter_buddy_dev_energy", buckets)

    assert meta["statistic_id"] == "sensor.meter_buddy_dev_energy"
    assert meta["has_sum"] is True
    assert meta["has_mean"] is False
    assert meta["mean_type"] == MEAN_TYPE_NONE
    assert meta["unit_class"] == "energy"
    assert meta["unit_of_measurement"] == "kWh"
    assert len(stats) == 2
    assert stats[0]["start"] < datetime.now(timezone.utc)
    assert stats[0]["sum"] == 10.5
    assert stats[0]["state"] == 10.5
    assert stats[1]["sum"] == 11.0
    assert stats[1]["state"] == 11.0


def test_map_power_statistics_mean() -> None:
    buckets = [
        {"start": "2024-08-01T10:00:00Z", "energy_kwh_sum": 50.0, "power_w_mean": 250.5},
        {"start": "2024-08-01T11:00:00Z", "energy_kwh_sum": 50.0, "power_w_mean": 0.0},
    ]
    meta, stats = map_power_statistics("sensor.meter_buddy_dev_power", buckets)

    assert meta["has_mean"] is True
    assert meta["mean_type"] == MEAN_TYPE_ARITHMETIC
    assert meta["has_sum"] is False
    assert meta["unit_class"] == "power"
    assert meta["unit_of_measurement"] == "W"
    assert stats[0]["mean"] == 250.5
    assert stats[1]["mean"] == 0.0
    assert "sum" not in stats[0]
    assert stats[0]["start"].year == 2024


def test_absolute_energy_kwh() -> None:
    assert absolute_energy_kwh({"energy_kwh": 187.25}) == 187.25


def test_is_hour_aligned() -> None:
    assert is_hour_aligned(datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc))
    assert not is_hour_aligned(datetime(2024, 7, 1, 12, 5, tzinfo=timezone.utc))


def test_is_five_min_aligned() -> None:
    assert is_five_min_aligned(datetime(2024, 7, 1, 12, 5, tzinfo=timezone.utc))
    assert is_five_min_aligned(datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc))
    assert not is_five_min_aligned(datetime(2024, 7, 1, 12, 7, tzinfo=timezone.utc))


def test_map_hour_align_skips_five_min_buckets() -> None:
    buckets = [
        {"start": "2024-07-01T00:00:00Z", "energy_kwh_sum": 10.0, "power_w_mean": 100.0},
        {"start": "2024-07-01T00:05:00Z", "energy_kwh_sum": 10.1, "power_w_mean": 50.0},
    ]
    _meta, energy_stats = map_energy_statistics(
        "sensor.meter_buddy_dev_energy", buckets, align="hour"
    )
    _meta, power_stats = map_power_statistics(
        "sensor.meter_buddy_dev_power", buckets, align="hour"
    )
    assert len(energy_stats) == 1
    assert energy_stats[0]["sum"] == 10.0
    assert len(power_stats) == 1
    assert power_stats[0]["mean"] == 100.0


def test_map_five_min_align_keeps_five_min_buckets() -> None:
    buckets = [
        {"start": "2024-07-01T00:00:00Z", "energy_kwh_sum": 10.0, "power_w_mean": 100.0},
        {"start": "2024-07-01T00:05:00Z", "energy_kwh_sum": 10.1, "power_w_mean": 50.0},
        {"start": "2024-07-01T00:07:00Z", "energy_kwh_sum": 10.2, "power_w_mean": 1.0},
    ]
    _meta, energy_stats = map_energy_statistics(
        "sensor.meter_buddy_dev_energy", buckets, align="5min"
    )
    _meta, power_stats = map_power_statistics(
        "sensor.meter_buddy_dev_power", buckets, align="5min"
    )
    assert len(energy_stats) == 2
    assert energy_stats[0]["sum"] == 10.0
    assert energy_stats[1]["sum"] == 10.1
    assert len(power_stats) == 2
    assert power_stats[1]["mean"] == 50.0
