from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.db import get_dump_json

router = APIRouter()


@router.get("/dumps/{dump_id}/preview")
def preview_dump(dump_id: int) -> Response:
    raw_json = get_dump_json(dump_id)
    if raw_json is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dump not found")

    return Response(
        content=raw_json,
        media_type="application/json",
    )


@router.get("/dumps/{dump_id}.json")
def download_dump(dump_id: int) -> Response:
    raw_json = get_dump_json(dump_id)
    if raw_json is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dump not found")

    return Response(
        content=raw_json,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="meter-buddy-dump-{dump_id}.json"'
        },
    )
