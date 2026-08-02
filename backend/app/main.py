from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes_db, routes_dumps, routes_pages, routes_upload, routes_ws
from app.core.auth import validate_auth_config
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_auth_config()
    init_db()
    yield


_enable_docs = os.getenv("METER_BUDDY_ENABLE_DOCS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

app = FastAPI(
    title="Meter Buddy Backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    openapi_url="/openapi.json" if _enable_docs else None,
)


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


app.include_router(routes_pages.router)
app.include_router(routes_upload.router)
app.include_router(routes_dumps.router)
app.include_router(routes_db.router)
app.include_router(routes_ws.router)
