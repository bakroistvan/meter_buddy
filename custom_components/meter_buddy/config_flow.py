"""Config flow for Meter Buddy."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MeterBuddyApiClient, MeterBuddyApiError
from .const import (
    CONF_BASE_URL,
    CONF_DEVICE_ID,
    CONF_IMPORT_SCHEMA,
    DEFAULT_IMPORT_SCHEMA,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _normalize_base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise vol.Invalid("Base URL must include http:// or https://")
    return url


class MeterBuddyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Meter Buddy."""

    VERSION = 1

    def __init__(self) -> None:
        self._base_url: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect backend URL and Basic Auth credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                base_url = _normalize_base_url(user_input[CONF_BASE_URL])
            except vol.Invalid:
                errors["base_url"] = "invalid_url"
                base_url = user_input[CONF_BASE_URL]
            else:
                session = async_get_clientsession(self.hass)
                client = MeterBuddyApiClient(
                    session,
                    base_url,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
                try:
                    devices = await client.async_get_devices()
                except MeterBuddyApiError as err:
                    _LOGGER.debug("Auth/devices failed: %s", err)
                    msg = str(err).lower()
                    if "password" in msg or "401" in msg:
                        errors["base"] = "invalid_auth"
                    else:
                        errors["base"] = "cannot_connect"
                except (aiohttp.ClientError, TimeoutError):
                    errors["base"] = "cannot_connect"
                else:
                    if not devices:
                        errors["base"] = "no_devices"
                    else:
                        self._base_url = base_url
                        self._username = user_input[CONF_USERNAME]
                        self._password = user_input[CONF_PASSWORD]
                        self._devices = devices
                        return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick device_id from GET /api/devices."""
        device_ids = sorted(
            {str(d["device_id"]) for d in self._devices if d.get("device_id")}
        )
        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(device_ids)})

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Meter Buddy ({device_id})",
                data={
                    CONF_BASE_URL: self._base_url,
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_DEVICE_ID: device_id,
                    CONF_IMPORT_SCHEMA: DEFAULT_IMPORT_SCHEMA,
                },
            )

        return self.async_show_form(step_id="device", data_schema=schema)
