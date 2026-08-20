"""Unit tests for upload-session wait / import coordinator logic."""

from __future__ import annotations

from custom_components.meter_buddy.session import (
    ImportDecision,
    SessionTracker,
    apply_absolute_energy,
    should_force_full_rebuild,
)


DEVICE = "esp-aabb"


def _dump(*, last_batch: bool, session: str = "sess-1", device_id: str = DEVICE) -> dict:
    return {
        "device_id": device_id,
        "upload_session_id": session,
        "last_batch": last_batch,
        "dump_id": 1,
        "reading_count": 128,
    }


def test_ignore_other_device() -> None:
    tracker = SessionTracker()
    assert tracker.on_new_dump(_dump(last_batch=True, device_id="other"), DEVICE) is (
        ImportDecision.IGNORE
    )


def test_ignore_last_batch_false_no_import() -> None:
    tracker = SessionTracker()
    decision = tracker.on_new_dump(_dump(last_batch=False), DEVICE)
    assert decision is ImportDecision.WAIT
    assert tracker.pending_session_id == "sess-1"

    # Several mid-session dumps still wait
    assert tracker.on_new_dump(_dump(last_batch=False, session="sess-1"), DEVICE) is (
        ImportDecision.WAIT
    )


def test_import_once_on_last_batch_true() -> None:
    tracker = SessionTracker()
    tracker.on_new_dump(_dump(last_batch=False), DEVICE)
    decision = tracker.on_new_dump(_dump(last_batch=True), DEVICE)
    assert decision is ImportDecision.IMPORT
    assert tracker.pending_session_id is None


def test_timeout_path_imports() -> None:
    tracker = SessionTracker()
    tracker.on_new_dump(_dump(last_batch=False), DEVICE)
    assert tracker.mark_timeout() is ImportDecision.IMPORT
    assert tracker.pending_session_id is None


def test_timeout_without_pending_ignored() -> None:
    tracker = SessionTracker()
    assert tracker.mark_timeout() is ImportDecision.IGNORE


def test_absolute_energy_never_previous_plus_delta() -> None:
    previous = 12.0
    state = {"energy_kwh": 187.0, "power_w": 0.0}
    # Would be wrong if we did previous + (187-12) incorrectly as previous+187
    assert apply_absolute_energy(previous, state) == 187.0
    assert apply_absolute_energy(None, state) == 187.0
    assert apply_absolute_energy(200.0, {"energy_kwh": 50.0}) == 50.0


def test_import_schema_bump_forces_rebuild() -> None:
    assert should_force_full_rebuild(1, 2) is True
    assert should_force_full_rebuild(1, 1) is False
