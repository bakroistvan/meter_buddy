from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.core.auth import require_basic_auth
from app.db import db_path, init_db, replace_db_file, reset_db

router = APIRouter(dependencies=[Depends(require_basic_auth)])


@router.get("/db")
def download_db() -> FileResponse:
    path = db_path()
    if not path.exists():
        init_db()
    return FileResponse(
        path=path,
        media_type="application/x-sqlite3",
        filename="meter_buddy.sqlite3",
    )


@router.post("/db", status_code=status.HTTP_200_OK)
async def upload_db(
    request: Request,
    file: UploadFile | None = File(None),
) -> dict[str, str | bool]:
    if file is not None:
        content = await file.read()
    else:
        content = await request.body()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded",
        )
    try:
        replace_db_file(content)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    return {"ok": True, "message": "Database uploaded and initialized successfully"}


@router.delete("/db")
def delete_db() -> dict[str, str | bool]:
    reset_db()
    return {"ok": True, "message": "Database deleted and re-initialized"}
