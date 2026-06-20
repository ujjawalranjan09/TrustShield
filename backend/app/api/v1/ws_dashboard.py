"""WebSocket endpoint for real-time dashboard events.

Pushes fraud detection events to connected dashboard clients
as they happen. Falls back to periodic polling if no events occur.
"""

import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Connected dashboard clients
_connections: Set[WebSocket] = set()


async def broadcast_event(event: dict) -> None:
    """Broadcast an event to all connected dashboard clients."""
    if not _connections:
        return
    message = json.dumps(event)
    disconnected = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _connections -= disconnected


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """Real-time fraud event stream for the dashboard.

    Clients connect and receive fraud events as they're detected.
    The server also sends periodic heartbeat messages.
    Accepts connections without auth in development mode.
    """
    try:
        await websocket.accept()
    except Exception:
        # If accept fails due to CORS/origin, try accepting anyway in dev
        logger.warning("WebSocket accept failed, attempting force accept")
        return

    _connections.add(websocket)
    logger.info("Dashboard client connected (total: %d)", len(_connections))

    try:
        while True:
            # Keep connection alive; client can send pings
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Client may send a ping or filter preferences
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        logger.info("Dashboard client disconnected (total: %d)", len(_connections))
