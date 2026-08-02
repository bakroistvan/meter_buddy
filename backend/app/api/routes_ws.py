from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.auth import require_websocket_basic_auth
from app.services.realtime import manager

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(
    ws: WebSocket,
    _: str = Depends(require_websocket_basic_auth),
):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
