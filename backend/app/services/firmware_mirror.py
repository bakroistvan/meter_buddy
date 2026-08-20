from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from semver import Version

logger = logging.getLogger(__name__)

USER_AGENT = "meter-buddy-firmware-mirror/1.0"
MANIFEST_NAME = "manifest.json"
BIN_NAME_RE = re.compile(r"^meter-buddy-fw-v.+\.bin$")
PARTITIONS_SUFFIX = "-partitions.bin"


@dataclass
class FirmwareRelease:
    tag: str
    published_at: str
    filename: str
    size: int
    md5: str


@dataclass
class SyncStatus:
    last_sync_at: str | None = None
    last_error: str | None = None
    last_ok: bool | None = None


def firmware_dir() -> Path:
    raw = os.getenv("METER_BUDDY_FIRMWARE_DIR", "").strip()
    if raw:
        return Path(raw)
    # Local default: backend/data/firmware (repo-relative when cwd is backend/)
    return Path(__file__).resolve().parents[2] / "data" / "firmware"


def github_repo() -> str:
    return os.getenv("METER_BUDDY_GITHUB_REPO", "bakroistvan/meter_buddy").strip() or (
        "bakroistvan/meter_buddy"
    )


def sync_interval_sec() -> float:
    raw = os.getenv("METER_BUDDY_FIRMWARE_SYNC_INTERVAL_SEC", "86400").strip()
    try:
        value = float(raw)
    except ValueError:
        return 86400.0
    return max(60.0, value)


def _github_token() -> str | None:
    token = os.getenv("METER_BUDDY_GITHUB_TOKEN", "").strip()
    return token or None


def parse_semver(version: str | None) -> Version | None:
    if version is None:
        return None
    text = version.strip()
    if not text:
        return None
    if text[0] in "vV":
        text = text[1:]
    try:
        return Version.parse(text)
    except ValueError:
        return None


def compare_semver(a: Version, b: Version) -> int:
    # Compare major.minor.patch only so git-describe strings (v0.4.0-5-g…)
    # match the release tag v0.4.0 for OTA 304 decisions.
    left = a.replace(prerelease=None, build=None)
    right = b.replace(prerelease=None, build=None)
    return left.compare(right)


def _semver_sort_key(version: str) -> Version:
    return parse_semver(version) or Version(0, 0, 0)


def _http_get(url: str, *, accept: str | None = None) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": accept or "application/vnd.github+json"}
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=60) as response:
        return response.read()


def _is_app_firmware_asset(name: str) -> bool:
    if name.endswith(PARTITIONS_SUFFIX):
        return False
    if name.endswith(".elf"):
        return False
    return BIN_NAME_RE.match(name) is not None


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


class FirmwareMirror:
    """Mirror GitHub release .bin assets onto local disk for HTTPUpdate."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._status = SyncStatus()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start_background_sync(self) -> None:
        if os.getenv("METER_BUDDY_FIRMWARE_DISABLE_SYNC", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="firmware-mirror",
            daemon=True,
        )
        self._thread.start()

    def stop_background_sync(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sync_now()
            except Exception:  # noqa: BLE001 — keep poller alive
                logger.exception("firmware mirror sync failed")
            self._stop.wait(sync_interval_sec())

    def sync_now(self) -> dict[str, Any]:
        with self._lock:
            try:
                releases = self._fetch_and_store()
                self._status = SyncStatus(
                    last_sync_at=_utcnow_iso(),
                    last_error=None,
                    last_ok=True,
                )
                return {
                    "ok": True,
                    "synced": len(releases),
                    "releases": [asdict(r) for r in releases],
                    "status": asdict(self._status),
                }
            except Exception as exc:  # noqa: BLE001
                self._status = SyncStatus(
                    last_sync_at=_utcnow_iso(),
                    last_error=str(exc),
                    last_ok=False,
                )
                logger.exception("firmware mirror sync error")
                return {
                    "ok": False,
                    "error": str(exc),
                    "status": asdict(self._status),
                }

    def _fetch_and_store(self) -> list[FirmwareRelease]:
        repo = github_repo()
        url = f"https://api.github.com/repos/{repo}/releases?per_page=30"
        try:
            raw = _http_get(url)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"GitHub releases HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub releases network error: {exc.reason}") from exc

        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("GitHub releases response was not a list")

        root = firmware_dir()
        root.mkdir(parents=True, exist_ok=True)

        mirrored: list[FirmwareRelease] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("draft") or item.get("prerelease"):
                continue
            tag = str(item.get("tag_name") or "").strip()
            if parse_semver(tag) is None:
                continue
            assets = item.get("assets") or []
            if not isinstance(assets, list):
                continue
            asset = next(
                (
                    a
                    for a in assets
                    if isinstance(a, dict) and _is_app_firmware_asset(str(a.get("name") or ""))
                ),
                None,
            )
            if asset is None:
                continue
            filename = str(asset["name"])
            download_url = str(asset.get("browser_download_url") or "")
            if not download_url:
                continue
            dest = root / filename
            if dest.is_file() and dest.stat().st_size == int(asset.get("size") or -1):
                md5 = _md5_bytes(dest.read_bytes())
            else:
                try:
                    bin_bytes = _http_get(download_url, accept="application/octet-stream")
                except HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="replace")[:200]
                    raise RuntimeError(
                        f"asset download HTTP {exc.code} for {filename}: {body}"
                    ) from exc
                dest.write_bytes(bin_bytes)
                md5 = _md5_bytes(bin_bytes)

            release = FirmwareRelease(
                tag=tag,
                published_at=str(item.get("published_at") or ""),
                filename=filename,
                size=dest.stat().st_size,
                md5=md5,
            )
            mirrored.append(release)

        mirrored.sort(key=lambda r: _semver_sort_key(r.tag), reverse=True)
        self._write_manifest(mirrored)
        return mirrored

    def _manifest_path(self) -> Path:
        return firmware_dir() / MANIFEST_NAME

    def _write_manifest(self, releases: list[FirmwareRelease]) -> None:
        path = self._manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _utcnow_iso(),
            "repo": github_repo(),
            "releases": [asdict(r) for r in releases],
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _read_manifest(self) -> list[FirmwareRelease]:
        path = self._manifest_path()
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        releases_raw = data.get("releases") if isinstance(data, dict) else None
        if not isinstance(releases_raw, list):
            return []
        out: list[FirmwareRelease] = []
        for item in releases_raw:
            if not isinstance(item, dict):
                continue
            try:
                out.append(
                    FirmwareRelease(
                        tag=str(item["tag"]),
                        published_at=str(item.get("published_at") or ""),
                        filename=str(item["filename"]),
                        size=int(item["size"]),
                        md5=str(item["md5"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        out.sort(key=lambda r: _semver_sort_key(r.tag), reverse=True)
        return out

    def list_status(self) -> dict[str, Any]:
        with self._lock:
            releases = self._read_manifest()
            return {
                "repo": github_repo(),
                "firmware_dir": str(firmware_dir()),
                "sync_interval_sec": sync_interval_sec(),
                "status": asdict(self._status),
                "releases": [asdict(r) for r in releases],
                "latest": asdict(releases[0]) if releases else None,
            }

    def latest_release(self) -> FirmwareRelease | None:
        with self._lock:
            releases = self._read_manifest()
            return releases[0] if releases else None

    def bin_path_for(self, release: FirmwareRelease) -> Path | None:
        path = firmware_dir() / release.filename
        if path.is_file():
            return path
        return None


mirror = FirmwareMirror()
