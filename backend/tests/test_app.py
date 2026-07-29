from __future__ import annotations

import base64
import importlib
import os

from fastapi.testclient import TestClient


def auth_header(user: str = "meter-buddy", password: str = "change-me") -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_upload_index_and_download(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    with TestClient(app.main.app) as client:
        payload = {
            "device_id": "meter-buddy-001",
            "meter_impulses_per_kwh": 1000,
            "upload_trigger": "button",
            "readings": [
                {
                    "timestamp": "2026-05-01T13:00:00Z",
                    "period_start": "2026-05-01T12:00:00Z",
                    "pulses": 42,
                    "battery_v": 3.87,
                    "battery_pct_est": 62,
                }
            ],
        }

        response = client.post(
            "/api/meter-buddy/upload",
            headers=auth_header(),
            json=payload,
        )
        assert response.status_code == 201
        assert response.json() == {"ok": True, "dump_id": 1, "stored_readings": 1}

        index = client.get("/")
        assert index.status_code == 200
        assert "meter-buddy-001" in index.text
        assert '"id": 1' in index.text

        dump = client.get("/dumps/1.json")
        assert dump.status_code == 200
        assert dump.headers["content-type"].startswith("application/json")
        assert 'filename="meter-buddy-dump-1.json"' in dump.headers["content-disposition"]
        assert dump.json()["readings"][0]["pulses"] == 42

        preview = client.get("/dumps/1/preview")
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("application/json")
        assert "content-disposition" not in preview.headers
        assert preview.json()["readings"][0]["pulses"] == 42

        missing = client.get("/dumps/999/preview")
        assert missing.status_code == 404


def test_delete_dump_and_bulk_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    payload = {
        "device_id": "meter-buddy-001",
        "meter_impulses_per_kwh": 1000,
        "upload_trigger": "button",
        "readings": [
            {
                "timestamp": "2026-05-01T13:00:00Z",
                "period_start": "2026-05-01T12:00:00Z",
                "pulses": 42,
                "battery_v": 3.87,
                "battery_pct_est": 62,
            }
        ],
    }

    with TestClient(app.main.app) as client:
        for _ in range(3):
            response = client.post(
                "/api/meter-buddy/upload",
                headers=auth_header(),
                json=payload,
            )
            assert response.status_code == 201

        delete_one = client.delete("/dumps/2")
        assert delete_one.status_code == 200
        assert delete_one.json() == {"ok": True, "deleted_id": 2}

        assert client.get("/dumps/2.json").status_code == 404
        assert client.get("/dumps/1.json").status_code == 200
        assert client.get("/dumps/3.json").status_code == 200

        delete_bulk = client.delete("/dumps?up_to_id=1")
        assert delete_bulk.status_code == 200
        assert delete_bulk.json() == {"ok": True, "deleted_count": 1}

        assert client.get("/dumps/1.json").status_code == 404
        assert client.get("/dumps/3.json").status_code == 200

        missing = client.delete("/dumps/999")
        assert missing.status_code == 404


def test_websocket_receives_new_dump_notification(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    with TestClient(app.main.app) as client:
        with client.websocket_connect("/ws") as ws:
            payload = {
                "device_id": "meter-buddy-002",
                "meter_impulses_per_kwh": 1000,
                "upload_trigger": "button",
                "readings": [
                    {
                        "timestamp": "2026-06-01T10:00:00Z",
                        "period_start": "2026-06-01T09:00:00Z",
                        "pulses": 10,
                        "battery_v": 3.9,
                        "battery_pct_est": 70,
                    }
                ],
            }
            response = client.post(
                "/api/meter-buddy/upload",
                headers=auth_header(),
                json=payload,
            )
            assert response.status_code == 201

            msg = ws.receive_json()
            assert msg["type"] == "new_dump"
            assert msg["dump"]["id"] == 1
            assert msg["dump"]["device_id"] == "meter-buddy-002"
            assert msg["dump"]["reading_count"] == 1


def test_invalid_auth_and_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    with TestClient(app.main.app) as client:
        response = client.post(
            "/api/meter-buddy/upload",
            headers=auth_header(password="wrong"),
            json={"device_id": "meter-buddy-001"},
        )
        assert response.status_code == 401

        response = client.post(
            "/api/meter-buddy/upload",
            headers=auth_header(),
            json={"device_id": "meter-buddy-001"},
        )
        assert response.status_code == 422

