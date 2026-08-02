from __future__ import annotations

import base64
import importlib
import sqlite3

from fastapi.testclient import TestClient


def auth_header(user: str = "meter-buddy", password: str = "change-me") -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_list_dumps_and_db_management_endpoints(tmp_path, monkeypatch):
    db_file = tmp_path / "meter_buddy.sqlite3"
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(db_file))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")

    import app.main

    importlib.reload(app.main)

    with TestClient(app.main.app) as client:
        # 1. Post a dump
        payload = {
            "device_id": "meter-buddy-001",
            "meter_impulses_per_kwh": 1000,
            "upload_trigger": "button",
            "battery_v": 3.87,
            "battery_pct_est": 62,
            "readings": [
                {
                    "timestamp": "2026-05-01T13:00:00Z",
                    "period_start": "2026-05-01T12:00:00Z",
                    "pulses": 42,
                }
            ],
        }
        res = client.post("/api/meter-buddy/upload", headers=auth_header(), json=payload)
        assert res.status_code == 201

        # 2. Endpoint 1: List dumps as JSON
        list_res = client.get("/dumps", headers=auth_header())
        assert list_res.status_code == 200
        dumps = list_res.json()
        assert len(dumps) == 1
        assert dumps[0]["id"] == 1
        assert dumps[0]["device_id"] == "meter-buddy-001"
        assert dumps[0]["battery_v"] == 3.87

        # 3. Endpoint 2: Download .db file
        download_res = client.get("/db", headers=auth_header())
        assert download_res.status_code == 200
        assert download_res.headers["content-type"].startswith("application/x-sqlite3")
        db_bytes = download_res.content
        assert len(db_bytes) > 0

        # 4. Endpoint 4: Delete .db file (reset DB)
        del_res = client.delete("/db", headers=auth_header())
        assert del_res.status_code == 200
        assert del_res.json()["ok"] is True

        # Verify DB is reset and empty
        empty_list = client.get("/dumps", headers=auth_header()).json()
        assert len(empty_list) == 0

        # 5. Endpoint 3: Upload new .db file
        upload_db_res = client.post(
            "/db",
            headers=auth_header(),
            files={"file": ("meter_buddy.sqlite3", db_bytes, "application/x-sqlite3")},
        )
        assert upload_db_res.status_code == 200
        assert upload_db_res.json()["ok"] is True

        # Verify restored data
        restored_dumps = client.get("/dumps", headers=auth_header()).json()
        assert len(restored_dumps) == 1
        assert restored_dumps[0]["id"] == 1

        # Error case: Upload invalid DB file
        invalid_res = client.post(
            "/db",
            headers=auth_header(),
            files={"file": ("corrupt.db", b"not a sqlite file", "application/octet-stream")},
        )
        assert invalid_res.status_code == 400
