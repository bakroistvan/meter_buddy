"""The Meter Buddy Home Assistant custom component."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import Platform
    from homeassistant.core import HomeAssistant
    from homeassistant.exceptions import ConfigEntryNotReady

    from .api import MeterBuddyApiError
    from .const import (
        CONF_IMPORT_SCHEMA,
        CONF_WATERMARK,
        DEFAULT_IMPORT_SCHEMA,
        DOMAIN,
    )
    from .coordinator import MeterBuddyCoordinator
    from .entity_ids import energy_entity_id, power_entity_id
    from .session import should_force_full_rebuild

    PLATFORMS: list[Platform] = [Platform.SENSOR]

    async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Set up Meter Buddy from a config entry."""
        hass.data.setdefault(DOMAIN, {})

        data = dict(entry.data)
        entry_schema = int(data.get(CONF_IMPORT_SCHEMA, DEFAULT_IMPORT_SCHEMA))
        if should_force_full_rebuild(entry_schema, DEFAULT_IMPORT_SCHEMA):
            data[CONF_IMPORT_SCHEMA] = DEFAULT_IMPORT_SCHEMA
            data.pop(CONF_WATERMARK, None)
            hass.config_entries.async_update_entry(entry, data=data)
            _LOGGER.info("import_schema bump → forcing full statistics rebuild")

        coordinator = MeterBuddyCoordinator(hass, entry)
        device_id = entry.data["device_id"]
        coordinator.set_statistic_entity_ids(
            energy_entity_id=energy_entity_id(device_id),
            power_entity_id=power_entity_id(device_id),
        )
        hass.data[DOMAIN][entry.entry_id] = coordinator

        try:
            await coordinator.async_initial_import()
        except MeterBuddyApiError as err:
            raise ConfigEntryNotReady(str(err)) from err

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        coordinator.start_websocket()
        return True

    async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """Unload a config entry."""
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            coordinator: MeterBuddyCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
            await coordinator.async_shutdown()
        return unload_ok

except ImportError:  # pragma: no cover — pure unit tests without Home Assistant
    pass
