"""HTTP/WS client for the Meter Buddy backend (Basic Auth)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncIterator
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

import aiohttp

_LOGGER = logging.getLogger(__name__)


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _ws_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/") + "/")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/ws", "", "", ""))


class MeterBuddyApiError(Exception):
    """Raised when the backend returns an unexpected response."""


class MeterBuddyApiClient:
    """Thin aiohttp wrapper around devices / state / statistics / WS."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/") + "/"
        self._auth_headers = _basic_auth_header(username, password)
        self._username = username
        self._password = password

    def _url(self, path: str, query: dict[str, str] | None = None) -> str:
        url = urljoin(self._base_url, path.lstrip("/"))
        if query:
            url = f"{url}?{urlencode(query)}"
        return url

    async def _get_json(self, path: str, query: dict[str, str] | None = None) -> Any:
        url = self._url(path, query)
        async with self._session.get(url, headers=self._auth_headers) as resp:
            if resp.status == 401:
                raise MeterBuddyApiError("Invalid username or password")
            if resp.status >= 400:
                text = await resp.text()
                raise MeterBuddyApiError(f"HTTP {resp.status}: {text[:200]}")
            return await resp.json()

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """GET /api/devices."""
        data = await self._get_json("api/devices")
        if not isinstance(data, list):
            raise MeterBuddyApiError("Expected list from /api/devices")
        return data

    async def async_get_state(self, device_id: str) -> dict[str, Any]:
        """GET /api/devices/{id}/state."""
        data = await self._get_json(f"api/devices/{device_id}/state")
        if not isinstance(data, dict):
            raise MeterBuddyApiError("Expected object from /state")
        return data

    async def async_get_statistics(
        self,
        device_id: str,
        *,
        bucket: str = "hour",
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        """GET /api/devices/{id}/statistics."""
        query: dict[str, str] = {"bucket": bucket}
        if since:
            query["since"] = since
        if until:
            query["until"] = until
        data = await self._get_json(f"api/devices/{device_id}/statistics", query)
        if not isinstance(data, dict):
            raise MeterBuddyApiError("Expected object from /statistics")
        return data

    async def async_listen_ws(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed JSON messages from /ws (Basic Auth)."""
        url = _ws_url(self._base_url)
        auth = aiohttp.BasicAuth(self._username, self._password)
        while True:
            try:
                async with self._session.ws_connect(
                    url, auth=auth, heartbeat=30
                ) as ws:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                payload = json.loads(msg.data)
                            except json.JSONDecodeError:
                                _LOGGER.debug("Ignoring non-JSON WS frame")
                                continue
                            if isinstance(payload, dict):
                                yield payload
                        elif msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — reconnect loop
                _LOGGER.exception("Meter Buddy WS disconnected; retrying")
            await asyncio.sleep(5)
