"""DataUpdateCoordinator for Meter Buddy."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeterBuddyApiClient, MeterBuddyApiError
from .const import (
    ATTR_BATTERY_PCT,
    ATTR_ENERGY_KWH,
    ATTR_LAST_TIMESTAMP,
    ATTR_POWER_W,
    CONF_BASE_URL,
    CONF_DEVICE_ID,
    CONF_IMPORT_SCHEMA,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_WATERMARK,
    DEFAULT_IMPORT_SCHEMA,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    SESSION_COMPLETE_TIMEOUT_SECONDS,
)
from .session import ImportDecision, SessionTracker, apply_absolute_energy
from .statistics import map_energy_statistics, map_power_statistics


_LOGGER = logging.getLogger(__name__)


class MeterBuddyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch live state; import recorder statistics after upload sessions complete."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.entry = entry
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self.import_schema: int = int(
            entry.data.get(CONF_IMPORT_SCHEMA, DEFAULT_IMPORT_SCHEMA)
        )
        self.watermark: str | None = entry.data.get(CONF_WATERMARK)
        self.api = MeterBuddyApiClient(
            async_get_clientsession(hass),
            entry.data[CONF_BASE_URL],
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
        )
        self._import_lock = asyncio.Lock()
        self._session = SessionTracker()
        self._timeout_task: asyncio.Task[None] | None = None
        self._ws_task: asyncio.Task[None] | None = None
        self._energy_entity_id: str | None = None
        self._power_entity_id: str | None = None

    def set_statistic_entity_ids(
        self, *, energy_entity_id: str, power_entity_id: str
    ) -> None:
        """Bind entity_ids used as statistic_id for async_import_statistics."""
        self._energy_entity_id = energy_entity_id
        self._power_entity_id = power_entity_id

    async def async_initial_import(self) -> None:
        """First install / setup: fetch /state + /statistics with no WS wait."""
        data = await self._async_import_snapshot(full=True, reason="setup")
        self.async_set_updated_data(data)

    def start_websocket(self) -> None:
        """Start the /ws listener after platforms are ready."""
        if self._ws_task is None or self._ws_task.done():
            self._ws_task = self.hass.async_create_background_task(
                self._ws_loop(), name=f"{DOMAIN}_ws_{self.device_id}"
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """10-minute fallback poll — treat as a complete snapshot."""
        try:
            return await self._async_import_snapshot(full=False, reason="poll")
        except MeterBuddyApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _ws_loop(self) -> None:
        async for message in self.api.async_listen_ws():
            if message.get("type") != "new_dump":
                continue
            dump = message.get("dump") or {}
            if not isinstance(dump, dict):
                continue
            await self._async_handle_new_dump(dump)

    async def _async_handle_new_dump(self, dump: dict[str, Any]) -> None:
        decision = self._session.on_new_dump(dump, self.device_id)
        if decision is ImportDecision.IGNORE:
            return
        if decision is ImportDecision.WAIT:
            self._restart_session_timeout()
            _LOGGER.debug(
                "Waiting for last_batch (session=%s)",
                self._session.pending_session_id,
            )
            return
        self._cancel_session_timeout()
        await self._async_import_snapshot(full=False, reason="last_batch")

    def _restart_session_timeout(self) -> None:
        self._cancel_session_timeout()

        async def _fire() -> None:
            try:
                await asyncio.sleep(SESSION_COMPLETE_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                return
            decision = self._session.mark_timeout()
            if decision is ImportDecision.IMPORT:
                _LOGGER.info(
                    "Upload session timeout for %s; importing stored stats",
                    self.device_id,
                )
                await self._async_import_snapshot(full=False, reason="timeout")

        self._timeout_task = self.hass.async_create_task(
            _fire(), name=f"{DOMAIN}_session_timeout"
        )

    def _cancel_session_timeout(self) -> None:
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    async def _async_import_snapshot(
        self, *, full: bool, reason: str
    ) -> dict[str, Any]:
        """Under lock: GET statistics + state, import stats, update sensors."""
        async with self._import_lock:
            since = None if full else self.watermark
            hourly = await self.api.async_get_statistics(
                self.device_id, bucket="hour", since=since
            )
            five_min = await self.api.async_get_statistics(
                self.device_id, bucket="5min", since=since
            )
            state = await self.api.async_get_state(self.device_id)

            await self._async_push_statistics(hourly, five_min)

            previous = None
            if self.data:
                previous = self.data.get(ATTR_ENERGY_KWH)
            energy = apply_absolute_energy(previous, state)

            data = {
                ATTR_ENERGY_KWH: energy,
                ATTR_POWER_W: float(state.get("power_w") or 0.0),
                ATTR_BATTERY_PCT: state.get("battery_pct_est"),
                ATTR_LAST_TIMESTAMP: state.get("last_timestamp"),
                "device_id": self.device_id,
                "import_reason": reason,
            }

            new_watermark = self._watermark_from_buckets(
                (hourly.get("buckets") or []) + (five_min.get("buckets") or [])
            )
            if new_watermark:
                self.watermark = new_watermark
                self._async_save_entry_data()

            self._session.clear()
            self.async_set_updated_data(data)
            _LOGGER.debug(
                "Imported snapshot reason=%s energy_kwh=%s watermark=%s",
                reason,
                energy,
                self.watermark,
            )
            return data

    async def _async_push_statistics(
        self,
        hourly: dict[str, Any],
        five_min: dict[str, Any],
    ) -> None:
        """Import hour → LTS and 5min → STS into the recorder.

        Public ``async_import_statistics`` only accepts top-of-hour rows (LTS).
        5-minute rows go to ``statistics_short_term`` via the recorder instance
        import path (same job used internally when the table arg is ShortTerm).
        """
        if not self._energy_entity_id or not self._power_entity_id:
            _LOGGER.debug("Skipping statistics import; entity_ids not bound yet")
            return

        try:
            from homeassistant.components.recorder import get_instance  # noqa: PLC0415
            from homeassistant.components.recorder.db_schema import (  # noqa: PLC0415
                StatisticsShortTerm,
            )
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                async_import_statistics,
            )
        except ImportError:
            _LOGGER.warning("Recorder statistics API unavailable; skipping import")
            return

        hour_buckets = list(hourly.get("buckets") or [])
        five_buckets = list(five_min.get("buckets") or [])

        if hour_buckets:
            energy_meta, energy_stats = map_energy_statistics(
                self._energy_entity_id,
                hour_buckets,
                name="Meter Buddy energy",
                align="hour",
            )
            power_meta, power_stats = map_power_statistics(
                self._power_entity_id,
                hour_buckets,
                name="Meter Buddy power",
                align="hour",
            )
            if energy_stats:
                async_import_statistics(self.hass, energy_meta, energy_stats)
            if power_stats:
                async_import_statistics(self.hass, power_meta, power_stats)

        if five_buckets:
            energy_meta, energy_stats = map_energy_statistics(
                self._energy_entity_id,
                five_buckets,
                name="Meter Buddy energy",
                align="5min",
            )
            power_meta, power_stats = map_power_statistics(
                self._power_entity_id,
                five_buckets,
                name="Meter Buddy power",
                align="5min",
            )
            recorder = get_instance(self.hass)
            # Materialize lists: the recorder queue may consume later on its thread.
            if energy_stats:
                recorder.async_import_statistics(
                    energy_meta, list(energy_stats), StatisticsShortTerm
                )
            if power_stats:
                recorder.async_import_statistics(
                    power_meta, list(power_stats), StatisticsShortTerm
                )

    @staticmethod
    def _watermark_from_buckets(buckets: list[dict[str, Any]]) -> str | None:
        if not buckets:
            return None
        latest: datetime | None = None
        for bucket in buckets:
            start = bucket.get("start")
            if not start:
                continue
            if isinstance(start, datetime):
                ts = start
            else:
                text = str(start).strip()
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                ts = datetime.fromisoformat(text)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if latest is None or ts > latest:
                latest = ts
        if latest is None:
            return None
        return latest.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @callback
    def _async_save_entry_data(self) -> None:
        data = {**self.entry.data, CONF_WATERMARK: self.watermark}
        self.hass.config_entries.async_update_entry(self.entry, data=data)

    async def async_shutdown(self) -> None:
        """Cancel WS and timeout tasks."""
        self._cancel_session_timeout()
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        await super().async_shutdown()
