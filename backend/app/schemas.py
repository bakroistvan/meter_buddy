from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MeterReading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    period_start: datetime | None = None
    pulses: int = Field(ge=0)


class UploadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=80)
    meter_impulses_per_kwh: int = Field(gt=0)
    upload_trigger: str | None = Field(default=None, max_length=40)
    battery_v: float | None = Field(default=None, ge=0)
    battery_pct_est: int | None = Field(default=None, ge=0, le=100)
    readings: list[MeterReading] = Field(default_factory=list)


class UploadResponse(BaseModel):
    ok: bool
    dump_id: int
    stored_readings: int

