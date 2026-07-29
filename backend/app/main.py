from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes_db, routes_dumps, routes_pages, routes_upload, routes_ws
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Meter Buddy Backend", version="0.1.0", lifespan=lifespan)
app.include_router(routes_pages.router)
app.include_router(routes_upload.router)
app.include_router(routes_dumps.router)
app.include_router(routes_db.router)
app.include_router(routes_ws.router)
