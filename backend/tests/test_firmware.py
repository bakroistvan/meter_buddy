from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

from tests.test_app import auth_header


@pytest.fixture
def firmware_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    fw_dir = tmp_path / "firmware"
    fw_dir.mkdir()
    monkeypatch.setenv("METER_BUDDY_DB_PATH", str(tmp_path / "meter_buddy.sqlite3"))
    monkeypatch.setenv("METER_BUDDY_AUTH_USER", "meter-buddy")
    monkeypatch.setenv("METER_BUDDY_AUTH_PASSWORD", "change-me")
    monkeypatch.setenv("METER_BUDDY_FIRMWARE_DIR", str(fw_dir))
    monkeypatch.setenv("METER_BUDDY_FIRMWARE_DISABLE_SYNC", "1")
    monkeypatch.setenv("METER_BUDDY_GITHUB_REPO", "bakroistvan/meter_buddy")
    return fw_dir


def _reload_app():
    import app.main
    from app.services import firmware_mirror

    importlib.reload(firmware_mirror)
    importlib.reload(app.main)
    return app.main, firmware_mirror


def _seed_release(fw_dir: Path, *, tag: str = "v0.4.0", payload: bytes = b"firmware-bytes") -> str:
    filename = f"meter-buddy-fw-{tag}.bin"
    path = fw_dir / filename
    path.write_bytes(payload)
    md5 = hashlib.md5(payload).hexdigest()
    manifest = {
        "updated_at": "2026-08-03T20:22:00Z",
        "repo": "bakroistvan/meter_buddy",
        "releases": [
            {
                "tag": tag,
                "published_at": "2026-08-03T20:22:00Z",
                "filename": filename,
                "size": len(payload),
                "md5": md5,
            }
        ],
    }
    (fw_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return md5


def test_firmware_routes_require_auth(firmware_env):
    app_main, _ = _reload_app()
    with TestClient(app_main.app) as client:
        assert client.get("/api/meter-buddy/firmware").status_code == 401
        assert client.get("/api/meter-buddy/firmware/version").status_code == 401
        assert client.post("/api/meter-buddy/firmware/sync").status_code == 401


def test_firmware_version_503_when_empty(firmware_env):
    app_main, _ = _reload_app()
    with TestClient(app_main.app) as client:
        response = client.get(
            "/api/meter-buddy/firmware/version",
            headers={**auth_header(), "x-ESP32-version": "0.3.0"},
        )
        assert response.status_code == 503


def test_firmware_version_304_when_current(firmware_env):
    md5 = _seed_release(firmware_env, tag="v0.4.0")
    app_main, _ = _reload_app()
    with TestClient(app_main.app) as client:
        for version in ("0.4.0", "v0.4.0", "0.5.0"):
            response = client.get(
                "/api/meter-buddy/firmware/version",
                headers={**auth_header(), "x-ESP32-version": version},
            )
            assert response.status_code == 304, version
        # ensure seed md5 is still the expected one for the newer-path test below
        assert len(md5) == 32


def test_firmware_version_200_with_md5_when_older(firmware_env):
    payload = b"ota-image-v040"
    md5 = _seed_release(firmware_env, tag="v0.4.0", payload=payload)
    app_main, _ = _reload_app()
    with TestClient(app_main.app) as client:
        response = client.get(
            "/api/meter-buddy/firmware/version",
            headers={**auth_header(), "x-ESP32-version": "0.3.0"},
        )
        assert response.status_code == 200
        assert response.content == payload
        assert response.headers.get("x-md5") == md5 or response.headers.get("x-MD5") == md5
        assert response.headers["content-type"].startswith("application/octet-stream")


def test_firmware_list_shows_mirrored(firmware_env):
    _seed_release(firmware_env, tag="v0.4.0")
    app_main, _ = _reload_app()
    with TestClient(app_main.app) as client:
        response = client.get("/api/meter-buddy/firmware", headers=auth_header())
        assert response.status_code == 200
        body = response.json()
        assert body["latest"]["tag"] == "v0.4.0"
        assert body["releases"][0]["filename"] == "meter-buddy-fw-v0.4.0.bin"


def test_firmware_sync_mirrors_github(firmware_env, monkeypatch: pytest.MonkeyPatch):
    bin_payload = b"synced-from-github"
    releases_json = json.dumps(
        [
            {
                "tag_name": "v0.4.0",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-08-03T20:22:00Z",
                "assets": [
                    {
                        "name": "meter-buddy-fw-v0.4.0.bin",
                        "size": len(bin_payload),
                        "browser_download_url": "https://example.test/meter-buddy-fw-v0.4.0.bin",
                    },
                    {
                        "name": "meter-buddy-fw-v0.4.0-partitions.bin",
                        "size": 10,
                        "browser_download_url": "https://example.test/partitions.bin",
                    },
                    {
                        "name": "meter-buddy-fw-v0.4.0.elf",
                        "size": 20,
                        "browser_download_url": "https://example.test/elf",
                    },
                ],
            },
            {
                "tag_name": "v0.3.0",
                "draft": False,
                "prerelease": True,
                "published_at": "2026-07-01T00:00:00Z",
                "assets": [
                    {
                        "name": "meter-buddy-fw-v0.3.0.bin",
                        "size": 3,
                        "browser_download_url": "https://example.test/old.bin",
                    }
                ],
            },
        ]
    ).encode("utf-8")

    def fake_urlopen(request: Request, timeout: float = 60):  # noqa: ARG001
        url = request.full_url

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *args: Any):
                return False

            def read(self) -> bytes:
                if "api.github.com" in url and "/releases" in url:
                    return releases_json
                if url.endswith(".bin") and "partitions" not in url and not url.endswith(".elf"):
                    return bin_payload
                raise AssertionError(f"unexpected url {url}")

        return _Resp()

    app_main, firmware_mirror = _reload_app()
    monkeypatch.setattr(firmware_mirror, "urlopen", fake_urlopen)

    with TestClient(app_main.app) as client:
        response = client.post("/api/meter-buddy/firmware/sync", headers=auth_header())
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["synced"] == 1
        assert body["releases"][0]["tag"] == "v0.4.0"

        listed = client.get("/api/meter-buddy/firmware", headers=auth_header()).json()
        assert listed["latest"]["tag"] == "v0.4.0"
        assert listed["latest"]["md5"] == hashlib.md5(bin_payload).hexdigest()

        version = client.get(
            "/api/meter-buddy/firmware/version",
            headers={**auth_header(), "x-ESP32-version": "0.2.0"},
        )
        assert version.status_code == 200
        assert version.content == bin_payload


def test_firmware_sync_github_error(firmware_env, monkeypatch: pytest.MonkeyPatch):
    import io

    def boom(request: Request, timeout: float = 60):  # noqa: ARG001
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"API rate limit exceeded"}'),
        )

    app_main, firmware_mirror = _reload_app()
    monkeypatch.setattr(firmware_mirror, "urlopen", boom)

    with TestClient(app_main.app) as client:
        response = client.post("/api/meter-buddy/firmware/sync", headers=auth_header())
        assert response.status_code == 502


def test_parse_semver_describe_prefix():
    from semver import Version

    from app.services.firmware_mirror import compare_semver, parse_semver

    assert parse_semver("v0.4.0") == Version.parse("0.4.0")
    assert parse_semver("0.4.0") == Version.parse("0.4.0")
    assert parse_semver("v0.4.0-5-gabcdef") == Version.parse("0.4.0-5-gabcdef")
    assert parse_semver("not-a-version") is None
    assert compare_semver(Version.parse("0.4.0"), Version.parse("0.3.0")) == 1
    assert compare_semver(Version.parse("0.4.0-5-gabcdef"), Version.parse("0.4.0")) == 0


@pytest.mark.live_github
def test_live_github_mirrors_latest_release(firmware_env, monkeypatch: pytest.MonkeyPatch):
    """Opt-in: real GitHub Releases download. Skipped unless METER_BUDDY_LIVE_GITHUB=1."""
    if os.getenv("METER_BUDDY_LIVE_GITHUB", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set METER_BUDDY_LIVE_GITHUB=1 to hit real GitHub Releases")

    # Keep optional token from the environment (rate limits / private repos).
    token = os.getenv("METER_BUDDY_GITHUB_TOKEN", "").strip()
    if token:
        monkeypatch.setenv("METER_BUDDY_GITHUB_TOKEN", token)
    else:
        monkeypatch.delenv("METER_BUDDY_GITHUB_TOKEN", raising=False)

    app_main, _ = _reload_app()
    with TestClient(app_main.app) as client:
        sync = client.post("/api/meter-buddy/firmware/sync", headers=auth_header())
        assert sync.status_code == 200, sync.text
        body = sync.json()
        assert body["ok"] is True
        assert body["synced"] >= 1
        assert body["releases"]

        latest = body["releases"][0]
        assert latest["tag"].lstrip("vV")
        assert latest["filename"].startswith("meter-buddy-fw-v")
        assert latest["filename"].endswith(".bin")
        assert not latest["filename"].endswith("-partitions.bin")
        assert latest["size"] > 0
        assert len(latest["md5"]) == 32

        bin_path = firmware_env / latest["filename"]
        assert bin_path.is_file()
        data = bin_path.read_bytes()
        assert len(data) == latest["size"]
        assert hashlib.md5(data).hexdigest() == latest["md5"]

        listed = client.get("/api/meter-buddy/firmware", headers=auth_header())
        assert listed.status_code == 200
        assert listed.json()["latest"]["tag"] == latest["tag"]

        # Older than latest → stream the mirrored image.
        ota = client.get(
            "/api/meter-buddy/firmware/version",
            headers={**auth_header(), "x-ESP32-version": "0.0.0"},
        )
        assert ota.status_code == 200
        assert ota.content == data
        assert (ota.headers.get("x-md5") or ota.headers.get("x-MD5")) == latest["md5"]

        # Already on latest → 304.
        current = client.get(
            "/api/meter-buddy/firmware/version",
            headers={**auth_header(), "x-ESP32-version": latest["tag"]},
        )
        assert current.status_code == 304
