from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from test_app import auth_header


DEVICE_ID = "meter-buddy-ha-001"
SESSION_ID = "sess-abc123"
C = 1000


def _reload_app(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)
    return app.main


def _minute_reading(start: datetime, pulses: int = 10) -> dict:
    end = start + timedelta(seconds=60)
    return {
        "timestamp": end.isoformat().replace("+00:00", "Z"),
        "period_start": start.isoformat().replace("+00:00", "Z"),
        "pulses": pulses,
    }


def _build_readings(count: int, start: datetime, pulses: int = 10) -> list[dict]:
    return [_minute_reading(start + timedelta(minutes=i), pulses=pulses) for i in range(count)]


def test_session_batches_state_statistics_and_ws(tmp_path, monkeypatch):
    main = _reload_app(tmp_path, monkeypatch)
    start = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)

    batch1 = _build_readings(128, start, pulses=10)
    batch2 = _build_readings(128, start + timedelta(minutes=128), pulses=10)
    batch3 = _build_readings(44, start + timedelta(minutes=256), pulses=10)
    assert len(batch1) + len(batch2) + len(batch3) == 300

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws", headers=auth_header()) as ws:
            energies: list[float] = []

            for idx, (readings, last_batch) in enumerate(
                [
                    (batch1, False),
                    (batch2, False),
                    (batch3, True),
                ],
                start=1,
            ):
                payload = {
                    "device_id": DEVICE_ID,
                    "meter_impulses_per_kwh": C,
                    "upload_trigger": "button",
                    "upload_session_id": SESSION_ID,
                    "last_batch": last_batch,
                    "battery_v": 3.9,
                    "battery_pct_est": 70,
                    "readings": readings,
                }
                response = client.post(
                    "/api/meter-buddy/upload",
                    headers=auth_header(),
                    json=payload,
                )
                assert response.status_code == 201
                assert response.json()["stored_readings"] == len(readings)

                msg = ws.receive_json()
                assert msg["type"] == "new_dump"
                assert msg["dump"]["id"] == idx
                assert msg["dump"]["device_id"] == DEVICE_ID
                assert msg["dump"]["upload_session_id"] == SESSION_ID
                assert msg["dump"]["last_batch"] is last_batch
                assert msg["dump"]["reading_count"] == len(readings)

                state = client.get(
                    f"/api/devices/{DEVICE_ID}/state",
                    headers=auth_header(),
                )
                assert state.status_code == 200
                body = state.json()
                energies.append(body["energy_kwh"])
                assert body["device_id"] == DEVICE_ID
                assert body["meter_impulses_per_kwh"] == C

            assert energies[0] < energies[1] < energies[2]
            # 300 readings * 10 pulses / 1000 = 3.0 kWh
            assert energies[2] == pytest.approx(3.0)

            devices = client.get("/api/devices", headers=auth_header())
            assert devices.status_code == 200
            assert devices.json() == [
                {
                    "device_id": DEVICE_ID,
                    "last_seen": devices.json()[0]["last_seen"],
                    "reading_count": 300,
                }
            ]

            stats = client.get(
                f"/api/devices/{DEVICE_ID}/statistics",
                headers=auth_header(),
                params={"bucket": "hour"},
            )
            assert stats.status_code == 200
            stats_body = stats.json()
            assert stats_body["device_id"] == DEVICE_ID
            buckets = stats_body["buckets"]
            assert buckets
            # Historical starts — first reading hour is 08:00 UTC on 2026-05-01
            assert buckets[0]["start"] == "2026-05-01T08:00:00Z"
            assert not buckets[0]["start"].startswith("2026-08")
            assert buckets[-1]["energy_kwh_sum"] == pytest.approx(3.0)

            # Mid-session dumps listed with flags
            dumps = client.get("/dumps", headers=auth_header()).json()
            by_id = {d["id"]: d for d in dumps}
            assert by_id[1]["last_batch"] is False
            assert by_id[2]["last_batch"] is False
            assert by_id[3]["last_batch"] is True
            assert by_id[1]["upload_session_id"] == SESSION_ID


def test_heartbeat_empty_last_batch_true(tmp_path, monkeypatch):
    main = _reload_app(tmp_path, monkeypatch)

    with TestClient(main.app) as client:
        with client.websocket_connect("/ws", headers=auth_header()) as ws:
            # Seed one reading so statistics exist beforehand
            seed = {
                "device_id": DEVICE_ID,
                "meter_impulses_per_kwh": C,
                "upload_session_id": "seed-session",
                "last_batch": True,
                "readings": [
                    _minute_reading(
                        datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
                        pulses=1000,
                    )
                ],
            }
            assert (
                client.post(
                    "/api/meter-buddy/upload",
                    headers=auth_header(),
                    json=seed,
                ).status_code
                == 201
            )
            ws.receive_json()

            before = client.get(
                f"/api/devices/{DEVICE_ID}/statistics",
                headers=auth_header(),
                params={"bucket": "hour"},
            ).json()

            heartbeat = {
                "device_id": DEVICE_ID,
                "meter_impulses_per_kwh": C,
                "upload_trigger": "button",
                "upload_session_id": "hb-session",
                "last_batch": True,
                "battery_v": 3.85,
                "battery_pct_est": 60,
                "readings": [],
            }
            response = client.post(
                "/api/meter-buddy/upload",
                headers=auth_header(),
                json=heartbeat,
            )
            assert response.status_code == 201
            assert response.json()["stored_readings"] == 0

            msg = ws.receive_json()
            assert msg["dump"]["upload_session_id"] == "hb-session"
            assert msg["dump"]["last_batch"] is True
            assert msg["dump"]["reading_count"] == 0

            after = client.get(
                f"/api/devices/{DEVICE_ID}/statistics",
                headers=auth_header(),
                params={"bucket": "hour"},
            ).json()
            assert after["buckets"] == before["buckets"]

            state = client.get(
                f"/api/devices/{DEVICE_ID}/state",
                headers=auth_header(),
            ).json()
            assert state["energy_kwh"] == 1.0
            assert state["battery_v"] == 3.85


def test_incomplete_session_statistics_still_available(tmp_path, monkeypatch):
    main = _reload_app(tmp_path, monkeypatch)
    start = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    with TestClient(main.app) as client:
        payload = {
            "device_id": DEVICE_ID,
            "meter_impulses_per_kwh": C,
            "upload_session_id": "incomplete",
            "last_batch": False,
            "readings": _build_readings(10, start, pulses=100),
        }
        assert (
            client.post(
                "/api/meter-buddy/upload",
                headers=auth_header(),
                json=payload,
            ).status_code
            == 201
        )

        stats = client.get(
            f"/api/devices/{DEVICE_ID}/statistics",
            headers=auth_header(),
            params={"bucket": "5min"},
        )
        assert stats.status_code == 200
        buckets = stats.json()["buckets"]
        assert buckets
        assert buckets[0]["start"] == "2026-06-01T12:00:00Z"
        assert buckets[-1]["energy_kwh_sum"] == 1.0
