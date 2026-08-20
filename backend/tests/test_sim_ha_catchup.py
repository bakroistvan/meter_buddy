"""E2E: firmware-like multi-POST session → /statistics → HA import stub."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_app import auth_header

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.meter_buddy.statistics import (  # noqa: E402
    absolute_energy_kwh,
    map_energy_statistics,
    map_power_statistics,
)
from tools.ha_catchup import chunk_upload_batches, generate_sparse_readings  # noqa: E402

DEVICE_ID = "meter-buddy-sim-001"
C = 1000
ENTITY_ENERGY = f"sensor.meter_buddy_{DEVICE_ID.replace('-', '_')}_energy"
ENTITY_POWER = f"sensor.meter_buddy_{DEVICE_ID.replace('-', '_')}_power"


def _reload_app(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)
    return app.main


def test_sim_ha_catchup_session_to_statistics_stub(tmp_path, monkeypatch):
    main = _reload_app(tmp_path, monkeypatch)

    start = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)  # 6h sparse window
    readings = generate_sparse_readings(
        start,
        end,
        impulses_per_kwh=C,
        pulse_probability=0.4,
        pulses_when_active=10,
        seed=42,
    )
    assert len(readings) > 128  # forces multi-batch
    expected_kwh = sum(r["pulses"] for r in readings) / C

    batches = chunk_upload_batches(
        readings,
        device_id=DEVICE_ID,
        impulses_per_kwh=C,
        session_id="sim-catchup-session-001",
    )
    assert len(batches) >= 2
    assert all(b["upload_session_id"] == "sim-catchup-session-001" for b in batches)
    assert [b["last_batch"] for b in batches] == [False] * (len(batches) - 1) + [True]

    import_calls = 0

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws", headers=auth_header()) as ws:
            for idx, body in enumerate(batches):
                response = client.post(
                    "/api/meter-buddy/upload",
                    headers=auth_header(),
                    json=body,
                )
                assert response.status_code == 201

                msg = ws.receive_json()
                assert msg["type"] == "new_dump"
                assert msg["dump"]["device_id"] == DEVICE_ID
                assert msg["dump"]["upload_session_id"] == "sim-catchup-session-001"
                assert msg["dump"]["last_batch"] is body["last_batch"]

                # HA waits until last_batch — only then import once.
                if not body["last_batch"]:
                    continue

                import_calls += 1
                state = client.get(
                    f"/api/devices/{DEVICE_ID}/state",
                    headers=auth_header(),
                ).json()
                stats = client.get(
                    f"/api/devices/{DEVICE_ID}/statistics",
                    headers=auth_header(),
                    params={"bucket": "hour"},
                ).json()

                live_kwh = absolute_energy_kwh(state)
                assert live_kwh == pytest.approx(expected_kwh)
                assert state["energy_kwh"] == pytest.approx(expected_kwh)

                buckets = stats["buckets"]
                assert buckets, "expected at least one hour bucket"
                ingest_now = datetime.now(timezone.utc)
                for bucket in buckets:
                    start_ts = datetime.fromisoformat(
                        bucket["start"].replace("Z", "+00:00")
                    )
                    assert start_ts.year == 2026 and start_ts.month == 5 and start_ts.day == 1
                    assert start_ts < ingest_now
                    assert start.date() <= start_ts.date() <= end.date()

                # Idle hours inside the span have 0 W mean.
                assert any(b["power_w_mean"] == 0.0 for b in buckets) or all(
                    b["power_w_mean"] > 0 for b in buckets
                )

                _energy_meta, energy_rows = map_energy_statistics(
                    ENTITY_ENERGY, buckets
                )
                _power_meta, power_rows = map_power_statistics(ENTITY_POWER, buckets)
                assert len(energy_rows) == len(buckets)
                assert len(power_rows) == len(buckets)
                assert energy_rows[-1]["sum"] == pytest.approx(expected_kwh)
                for row in energy_rows:
                    assert row["start"].tzinfo is not None
                    assert row["start"] < ingest_now

    assert import_calls == 1
