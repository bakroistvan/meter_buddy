from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import FileResponse

from app.core.auth import require_basic_auth
from app.services.firmware_mirror import compare_semver, mirror, parse_semver

router = APIRouter()


@router.get("/api/meter-buddy/firmware")
def list_firmware(_: Annotated[str, Depends(require_basic_auth)]) -> dict:
    return mirror.list_status()


@router.post("/api/meter-buddy/firmware/sync")
def sync_firmware(_: Annotated[str, Depends(require_basic_auth)]) -> dict:
    result = mirror.sync_now()
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error") or "firmware sync failed",
        )
    return result


@router.get("/api/meter-buddy/firmware/version")
def firmware_version_for_httpupdate(
    _: Annotated[str, Depends(require_basic_auth)],
    x_esp32_version: Annotated[str | None, Header(alias="x-ESP32-version")] = None,
) -> Response:
    """Arduino HTTPUpdate protocol: 304 if current, else stream latest .bin with x-MD5."""
    latest = mirror.latest_release()
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no mirrored firmware available",
        )

    latest_semver = parse_semver(latest.tag)
    if latest_semver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mirrored firmware has invalid version tag",
        )

    current = parse_semver(x_esp32_version)
    # Strict semver when parseable; unparseable device version is treated as older
    # so a stale config fallback can still receive a real tagged image once.
    if current is not None and compare_semver(current, latest_semver) >= 0:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    path = mirror.bin_path_for(latest)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mirrored firmware file missing on disk",
        )

    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename=latest.filename,
        headers={
            "x-MD5": latest.md5,
        },
    )
