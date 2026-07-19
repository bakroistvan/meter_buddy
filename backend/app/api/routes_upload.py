from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.auth import require_basic_auth
from app.db import get_dump_meta, store_upload
from app.schemas import UploadPayload, UploadResponse
from app.services.realtime import manager

router = APIRouter()


@router.post(
    "/api/meter-buddy/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dump(
    payload: UploadPayload,
    _: Annotated[str, Depends(require_basic_auth)],
) -> UploadResponse:
    dump_id, stored_readings = store_upload(payload)
    meta = get_dump_meta(dump_id)
    if meta is not None:
        await manager.broadcast({"type": "new_dump", "dump": meta})
    return UploadResponse(ok=True, dump_id=dump_id, stored_readings=stored_readings)
