from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import require_basic_auth
from app.db import (
    device_exists,
    get_device_state_row,
    list_device_readings_debug,
    list_device_sparse_readings,
    list_devices,
)
from app.services.statistics import (
    aggregate_statistics,
    last_period_power_w,
    total_energy_kwh,
)

router = APIRouter(
    prefix="/api/devices",
    dependencies=[Depends(require_basic_auth)],
)

BucketParam = Literal["hour", "5min"]


def _iso_z(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@router.get("")
def get_devices() -> list[dict]:
    return list_devices()


@router.get("/{device_id}/state")
def get_device_state(device_id: str) -> dict:
    if not device_exists(device_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    state_row = get_device_state_row(device_id)
    assert state_row is not None

    readings = list_device_sparse_readings(device_id)
    energy_kwh = total_energy_kwh(readings)
    power = last_period_power_w(readings)

    battery_pct = state_row["battery_pct_est"]
    if battery_pct is not None:
        battery_pct = int(battery_pct)

    return {
        "device_id": device_id,
        "energy_kwh": energy_kwh,
        "power_w": 0.0 if power is None else power,
        "last_timestamp": state_row["last_timestamp"],
        "meter_impulses_per_kwh": state_row["meter_impulses_per_kwh"],
        "battery_v": state_row["battery_v"],
        "battery_pct_est": battery_pct,
    }


@router.get("/{device_id}/statistics")
def get_device_statistics(
    device_id: str,
    bucket: Annotated[BucketParam, Query()] = "hour",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> dict:
    if not device_exists(device_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    # Load all readings so cumulative energy before `since` is correct.
    readings = list_device_sparse_readings(device_id)
    buckets = aggregate_statistics(
        readings,
        bucket=bucket,
        since=since,
        until=until,
    )
    return {
        "device_id": device_id,
        "buckets": [
            {
                "start": _iso_z(b.start),
                "energy_kwh_sum": b.energy_kwh_sum,
                "power_w_mean": b.power_w_mean,
            }
            for b in buckets
        ],
    }


@router.get("/{device_id}/readings")
def get_device_readings(
    device_id: str,
    since: Annotated[datetime | None, Query()] = None,
) -> list[dict]:
    if not device_exists(device_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return list_device_readings_debug(device_id, since=since)
