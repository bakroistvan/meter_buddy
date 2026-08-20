"""Pure mappers from backend /statistics buckets to HA recorder statistics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

# Match homeassistant.components.recorder.models.statistics.StatisticMeanType
# so unit tests can run without Home Assistant installed.
MEAN_TYPE_NONE = 0
MEAN_TYPE_ARITHMETIC = 1

BucketAlign = Literal["hour", "5min"]


class StatisticMetaDict(TypedDict):
    """Subset of HA StatisticMetaData used by async_import_statistics."""

    has_mean: bool
    mean_type: int
    has_sum: bool
    name: str | None
    source: str
    statistic_id: str
    unit_class: str | None
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


def is_hour_aligned(start: datetime) -> bool:
    """True if start is usable by HA long-term statistics (top of hour)."""
    return start.minute == 0 and start.second == 0 and start.microsecond == 0


def is_five_min_aligned(start: datetime) -> bool:
    """True if start is usable by HA short-term statistics (5-minute grid)."""
    return (
        start.second == 0
        and start.microsecond == 0
        and start.minute % 5 == 0
    )


def _accepts_start(start: datetime, align: BucketAlign) -> bool:
    if align == "hour":
        return is_hour_aligned(start)
    return is_five_min_aligned(start)


def map_energy_statistics(
    entity_id: str,
    buckets: list[dict[str, Any]],
    *,
    name: str | None = None,
    align: BucketAlign = "hour",
) -> tuple[StatisticMetaDict, list[StatisticDataDict]]:
    """Map energy buckets to entity-linked HA statistics.

    Backend ``energy_kwh_sum`` is lifetime cumulative kWh at bucket end.
    HA ``sum`` and ``state`` both receive that absolute value (not a delta).

    ``align="hour"`` → long-term statistics table.
    ``align="5min"`` → short-term statistics table.
    """
    metadata: StatisticMetaDict = {
        "has_mean": False,
        "mean_type": MEAN_TYPE_NONE,
        "has_sum": True,
        "name": name,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }
    stats: list[StatisticDataDict] = []
    for bucket in buckets:
        start = parse_bucket_start(bucket["start"])
        if not _accepts_start(start, align):
            continue
        value = float(bucket["energy_kwh_sum"])
        stats.append(
            {
                "start": start,
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
    align: BucketAlign = "hour",
) -> tuple[StatisticMetaDict, list[StatisticDataDict]]:
    """Map power buckets to entity-linked HA statistics (mean watts)."""
    metadata: StatisticMetaDict = {
        "has_mean": True,
        "mean_type": MEAN_TYPE_ARITHMETIC,
        "has_sum": False,
        "name": name,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_class": "power",
        "unit_of_measurement": "W",
    }
    stats: list[StatisticDataDict] = []
    for bucket in buckets:
        start = parse_bucket_start(bucket["start"])
        if not _accepts_start(start, align):
            continue
        stats.append(
            {
                "start": start,
                "mean": float(bucket["power_w_mean"]),
            }
        )
    return metadata, stats


def absolute_energy_kwh(state: dict[str, Any]) -> float:
    """Live energy is the absolute backend total, never previous + delta."""
    return float(state["energy_kwh"])
