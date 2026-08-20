"""Helpers for stable entity_id / statistic_id values."""

from __future__ import annotations

import re


def slugify_device_id(device_id: str) -> str:
    """Slug suitable for HA object_id fragments."""
    text = device_id.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "device"


def energy_entity_id(device_id: str) -> str:
    return f"sensor.meter_buddy_{slugify_device_id(device_id)}_energy"


def power_entity_id(device_id: str) -> str:
    return f"sensor.meter_buddy_{slugify_device_id(device_id)}_power"


def battery_entity_id(device_id: str) -> str:
    return f"sensor.meter_buddy_{slugify_device_id(device_id)}_battery"
