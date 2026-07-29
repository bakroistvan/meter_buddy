from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.db import delete_dump, delete_dumps_up_to, get_dump_json, list_dumps

router = APIRouter()


@router.get("/dumps")
def list_dumps_endpoint() -> list[dict]:
    return [dict(row) for row in list_dumps()]



@router.get("/dumps/{dump_id}/preview")
def preview_dump(dump_id: int) -> Response:
    raw_json = get_dump_json(dump_id)
    if raw_json is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dump not found")

    return Response(
        content=raw_json,
        media_type="application/json",
    )


@router.delete("/dumps")
def delete_dumps_bulk(
    up_to_id: Annotated[int, Query(ge=1, description="Delete all dumps with ID <= this value")],
) -> dict[str, int | bool]:
    deleted_count = delete_dumps_up_to(up_to_id)
    return {"ok": True, "deleted_count": deleted_count}


@router.delete("/dumps/{dump_id}")
def delete_dump_route(dump_id: int) -> dict[str, int | bool]:
    if not delete_dump(dump_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dump not found")
    return {"ok": True, "deleted_id": dump_id}


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
