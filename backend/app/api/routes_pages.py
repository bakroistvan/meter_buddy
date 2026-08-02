from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.api.deps import templates
from app.core.auth import require_basic_auth
from app.db import list_dumps

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    _: Annotated[str, Depends(require_basic_auth)],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "dumps": [dict(row) for row in list_dumps()],
        },
    )
