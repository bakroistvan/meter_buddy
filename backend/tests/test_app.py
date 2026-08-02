from __future__ import annotations

import base64
import importlib
import os

import pytest

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

        index = client.get("/", headers=auth_header())
        assert index.status_code == 200
        assert "meter-buddy-001" in index.text
        assert '"id": 1' in index.text

        dump = client.get("/dumps/1.json", headers=auth_header())
        assert dump.status_code == 200
        assert dump.headers["content-type"].startswith("application/json")
        assert 'filename="meter-buddy-dump-1.json"' in dump.headers["content-disposition"]
        assert dump.json()["readings"][0]["pulses"] == 42

        preview = client.get("/dumps/1/preview", headers=auth_header())
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("application/json")
        assert "content-disposition" not in preview.headers
        assert preview.json()["readings"][0]["pulses"] == 42

        missing = client.get("/dumps/999/preview", headers=auth_header())
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

        delete_one = client.delete("/dumps/2", headers=auth_header())
        assert delete_one.status_code == 200
        assert delete_one.json() == {"ok": True, "deleted_id": 2}

        assert client.get("/dumps/2.json", headers=auth_header()).status_code == 404
        assert client.get("/dumps/1.json", headers=auth_header()).status_code == 200
        assert client.get("/dumps/3.json", headers=auth_header()).status_code == 200

        delete_bulk = client.delete("/dumps?up_to_id=1", headers=auth_header())
        assert delete_bulk.status_code == 200
        assert delete_bulk.json() == {"ok": True, "deleted_count": 1}

        assert client.get("/dumps/1.json", headers=auth_header()).status_code == 404
        assert client.get("/dumps/3.json", headers=auth_header()).status_code == 200

        missing = client.delete("/dumps/999", headers=auth_header())
        assert missing.status_code == 404


def test_websocket_receives_new_dump_notification(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    with TestClient(app.main.app) as client:
        with client.websocket_connect("/ws", headers=auth_header()) as ws:
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
            headers=auth_header("meter-buddy", "wrong-pass"),
            json={"device_id": "meter-buddy-001"},
        )
        assert response.status_code == 401

        response = client.post(
            "/api/meter-buddy/upload",
            headers=auth_header(),
            json={"device_id": "meter-buddy-001"},
        )
        assert response.status_code == 422


def test_empty_readings_with_errors_and_battery(tmp_path, monkeypatch):
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
            "battery_v": 3.87,
            "battery_pct_est": 62,
            "readings": [],
            "errors": [
                {"code": "no_data", "message": "no unsynced readings"},
                {
                    "code": "crc_mismatch",
                    "message": "record CRC failed",
                    "detail": "offset=64",
                },
            ],
        }

        response = client.post(
            "/api/meter-buddy/upload",
            headers=auth_header(),
            json=payload,
        )
        assert response.status_code == 201
        assert response.json() == {"ok": True, "dump_id": 1, "stored_readings": 0}

        dump = client.get("/dumps/1.json", headers=auth_header())
        assert dump.status_code == 200
        body = dump.json()
        assert body["readings"] == []
        assert body["battery_v"] == 3.87
        assert body["battery_pct_est"] == 62
        assert body["errors"][0]["code"] == "no_data"
        assert body["errors"][1]["detail"] == "offset=64"

        rejected = client.post(
            "/api/meter-buddy/upload",
            headers=auth_header(),
            json={
                "device_id": "meter-buddy-001",
                "meter_impulses_per_kwh": 1000,
                "readings": [],
                "errors": [
                    {
                        "code": "no_data",
                        "message": "no unsynced readings",
                        "extra_field": "nope",
                    }
                ],
            },
        )
        assert rejected.status_code == 422


def test_upload_omits_battery_fields(tmp_path, monkeypatch):
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

        dump = client.get("/dumps/1.json", headers=auth_header())
        assert dump.status_code == 200
        body = dump.json()
        assert "battery_v" not in body
        assert "battery_pct_est" not in body
        assert "battery_v" not in body["readings"][0]
        assert "battery_pct_est" not in body["readings"][0]

        dumps = client.get("/dumps", headers=auth_header()).json()
        assert dumps[0]["battery_v"] is None
        assert dumps[0]["battery_pct_est"] is None


def test_protected_routes_require_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    with TestClient(app.main.app) as client:
        assert client.get("/").status_code == 401
        assert client.get("/dumps").status_code == 401
        assert client.get("/db").status_code == 401
        assert client.get("/healthz").status_code == 200
        assert client.get("/healthz").json() == {"ok": True}
        try:
            with client.websocket_connect("/ws"):
                raise AssertionError("unauthenticated websocket should fail")
        except Exception:
            pass


def test_rejects_default_password_without_allow_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")
    monkeypatch.delenv("METER_BUDDY_ALLOW_INSECURE_AUTH", raising=False)

    import app.main

    importlib.reload(app.main)

    with pytest.raises(RuntimeError, match="METER_BUDDY_AUTH_PASSWORD"):
        with TestClient(app.main.app):
            pass
