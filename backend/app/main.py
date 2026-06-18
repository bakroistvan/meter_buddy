from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .auth import require_basic_auth
from .database import get_dump_json, get_dump_meta, init_db, list_dumps, store_upload
from .schemas import UploadPayload, UploadResponse


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Meter Buddy Backend", version="0.1.0", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "dumps": [dict(row) for row in list_dumps()],
        },
    )


@app.post(
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


@app.get("/dumps/{dump_id}/preview")
def preview_dump(dump_id: int) -> Response:
    raw_json = get_dump_json(dump_id)
    if raw_json is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dump not found")

    return Response(
        content=raw_json,
        media_type="application/json",
    )


@app.get("/dumps/{dump_id}.json")
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


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
