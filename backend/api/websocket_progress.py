import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["progress"])

_connections: dict[str, set[WebSocket]] = {}
_lock = asyncio.Lock()


async def broadcast_to_analysis(analysis_id: str, payload: dict[str, Any]) -> None:
    async with _lock:
        sockets = _connections.get(analysis_id, set()).copy()
    if not sockets:
        return
    msg = json.dumps(payload)
    dead: set[WebSocket] = set()
    for ws in sockets:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    if dead:
        async with _lock:
            live = _connections.get(analysis_id, set())
            live -= dead
            if not live:
                _connections.pop(analysis_id, None)


def emit_agent_status(
    analysis_id: str,
    agent_name: str,
    status: str,
    tool_call: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "agent_status",
        "agent_name": agent_name,
        "status": status,
    }
    if tool_call:
        payload["tool_call"] = tool_call
    asyncio.create_task(broadcast_to_analysis(analysis_id, payload))


@router.websocket("/analyses/{analysis_id}/progress")
async def websocket_progress(websocket: WebSocket, analysis_id: str) -> None:
    await websocket.accept()
    async with _lock:
        _connections.setdefault(analysis_id, set()).add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            live = _connections.get(analysis_id, set())
            live.discard(websocket)
            if not live:
                _connections.pop(analysis_id, None)
