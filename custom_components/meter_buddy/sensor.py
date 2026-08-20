"""Sensor platform for Meter Buddy."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BATTERY_PCT,
    ATTR_ENERGY_KWH,
    ATTR_POWER_W,
    CONF_DEVICE_ID,
    DOMAIN,
    SENSOR_BATTERY,
    SENSOR_ENERGY,
    SENSOR_POWER,
)
from .coordinator import MeterBuddyCoordinator
from .entity_ids import energy_entity_id, power_entity_id, slugify_device_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meter Buddy sensors from a config entry."""
    coordinator: MeterBuddyCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_id = entry.data[CONF_DEVICE_ID]

    power = MeterBuddyPowerSensor(coordinator, entry)
    energy = MeterBuddyEnergySensor(coordinator, entry)
    entities: list[SensorEntity] = [power, energy]

    if coordinator.data and coordinator.data.get(ATTR_BATTERY_PCT) is not None:
        entities.append(MeterBuddyBatterySensor(coordinator, entry))

    async_add_entities(entities)

    coordinator.set_statistic_entity_ids(
        energy_entity_id=energy_entity_id(device_id),
        power_entity_id=power_entity_id(device_id),
    )

    battery_added = any(
        getattr(ent, "_attr_unique_id", None) == f"{entry.unique_id}_{SENSOR_BATTERY}"
        for ent in entities
    )

    @callback
    def _maybe_add_battery() -> None:
        nonlocal battery_added
        if battery_added:
            return
        if not coordinator.data or coordinator.data.get(ATTR_BATTERY_PCT) is None:
            return
        battery = MeterBuddyBatterySensor(coordinator, entry)
        battery_added = True
        async_add_entities([battery])

    entry.async_on_unload(coordinator.async_add_listener(_maybe_add_battery))


class MeterBuddySensorBase(CoordinatorEntity[MeterBuddyCoordinator], SensorEntity):
    """Shared device info for Meter Buddy sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MeterBuddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        device_id = entry.data[CONF_DEVICE_ID]
        self._device_slug = slugify_device_id(device_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"Meter Buddy {device_id}",
            manufacturer="Meter Buddy",
            model="Logger",
        )


class MeterBuddyPowerSensor(MeterBuddySensorBase):
    """Instantaneous power in watts."""

    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, coordinator: MeterBuddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id}_{SENSOR_POWER}"
        self._attr_suggested_object_id = f"meter_buddy_{self._device_slug}_power"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(ATTR_POWER_W)
        return None if value is None else float(value)


class MeterBuddyEnergySensor(MeterBuddySensorBase):
    """Lifetime observed energy in kWh (absolute backend total)."""

    _attr_name = "Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator: MeterBuddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id}_{SENSOR_ENERGY}"
        self._attr_suggested_object_id = f"meter_buddy_{self._device_slug}_energy"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(ATTR_ENERGY_KWH)
        return None if value is None else float(value)


class MeterBuddyBatterySensor(MeterBuddySensorBase):
    """Optional estimated battery percentage."""

    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: MeterBuddyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id}_{SENSOR_BATTERY}"
        self._attr_suggested_object_id = f"meter_buddy_{self._device_slug}_battery"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(ATTR_BATTERY_PCT)
        return None if value is None else float(value)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data.get(ATTR_BATTERY_PCT) is not None
