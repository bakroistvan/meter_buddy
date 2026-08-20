"""Upload-session wait logic (unit-testable without Home Assistant)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ImportDecision(str, Enum):
    """What the coordinator should do after a WS new_dump."""

    WAIT = "wait"
    IMPORT = "import"
    IGNORE = "ignore"


@dataclass
class SessionTracker:
    """Track an in-progress ESP upload session until last_batch or timeout.

    Mid-session dumps (`last_batch: false`) only record the session id.
    Import runs once when `last_batch: true` arrives, or when
    :meth:`mark_timeout` is called after SESSION_COMPLETE_TIMEOUT_SECONDS.
    """

    pending_session_id: str | None = None
    _import_requested: bool = field(default=False, repr=False)

    def on_new_dump(self, dump: dict[str, Any], device_id: str) -> ImportDecision:
        """Handle one `new_dump` payload for this configured device."""
        if dump.get("device_id") != device_id:
            return ImportDecision.IGNORE

        last_batch = dump.get("last_batch")
        session_id = dump.get("upload_session_id")

        if last_batch is False:
            self.pending_session_id = session_id
            self._import_requested = False
            return ImportDecision.WAIT

        # last_batch true, missing, or any other truthy → complete snapshot
        self.pending_session_id = None
        self._import_requested = True
        return ImportDecision.IMPORT

    def mark_timeout(self) -> ImportDecision:
        """Timeout while waiting for last_batch → import whatever is stored."""
        if self.pending_session_id is None and not self._import_requested:
            # Timeout only applies while a mid-session wait is active
            return ImportDecision.IGNORE
        self.pending_session_id = None
        self._import_requested = True
        return ImportDecision.IMPORT

    def clear(self) -> None:
        """Reset after a successful import."""
        self.pending_session_id = None
        self._import_requested = False


def apply_absolute_energy(
    previous_energy_kwh: float | None,
    state: dict[str, Any],
) -> float:
    """Return live energy from /state; never previous + delta."""
    del previous_energy_kwh  # intentional: absolute overwrite
    return float(state["energy_kwh"])


def should_force_full_rebuild(entry_schema: int, code_schema: int) -> bool:
    """Bump of import_schema in config entry data forces a full statistics rebuild."""
    return int(entry_schema) != int(code_schema)
