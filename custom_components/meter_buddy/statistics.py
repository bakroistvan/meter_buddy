"""Pure mappers from backend /statistics buckets to HA recorder statistics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict


class StatisticMetaDict(TypedDict):
    """Subset of HA StatisticMetaData used by async_import_statistics."""

    has_mean: bool
    has_sum: bool
    name: str | None
    source: str
    statistic_id: str
    unit_of_measurement: str | None


class StatisticDataDict(TypedDict, total=False):
    """Subset of HA StatisticData used by async_import_statistics."""

    start: datetime
    mean: float
    sum: float
    state: float


def parse_bucket_start(value: str | datetime) -> datetime:
    """Parse a backend bucket start into an aware UTC datetime."""
    if isinstance(value, datetime):
        start = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        start = datetime.fromisoformat(text)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start.astimezone(timezone.utc)


def map_energy_statistics(
    entity_id: str,
    buckets: list[dict[str, Any]],
    *,
    name: str | None = None,
) -> tuple[StatisticMetaDict, list[StatisticDataDict]]:
    """Map energy buckets to entity-linked HA statistics.

    Backend ``energy_kwh_sum`` is lifetime cumulative kWh at bucket end.
    HA ``sum`` and ``state`` both receive that absolute value (not a delta).
    """
    metadata: StatisticMetaDict = {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_of_measurement": "kWh",
    }
    stats: list[StatisticDataDict] = []
    for bucket in buckets:
        value = float(bucket["energy_kwh_sum"])
        stats.append(
            {
                "start": parse_bucket_start(bucket["start"]),
                "sum": value,
                "state": value,
            }
        )
    return metadata, stats


def map_power_statistics(
    entity_id: str,
    buckets: list[dict[str, Any]],
    *,
    name: str | None = None,
) -> tuple[StatisticMetaDict, list[StatisticDataDict]]:
    """Map power buckets to entity-linked HA statistics (mean watts)."""
    metadata: StatisticMetaDict = {
        "has_mean": True,
        "has_sum": False,
        "name": name,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_of_measurement": "W",
    }
    stats: list[StatisticDataDict] = []
    for bucket in buckets:
        stats.append(
            {
                "start": parse_bucket_start(bucket["start"]),
                "mean": float(bucket["power_w_mean"]),
            }
        )
    return metadata, stats


def absolute_energy_kwh(state: dict[str, Any]) -> float:
    """Live energy is the absolute backend total, never previous + delta."""
    return float(state["energy_kwh"])
