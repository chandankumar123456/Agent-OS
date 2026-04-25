import asyncio
import urllib.parse
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect, Query
from ..orchestrator.v2.event_bus import event_bus, Event
from ..logs.logger import logger
from ..auth.utils import verify_access_token


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            # Limit concurrent connections per task
            if len(self.active_connections[task_id]) >= 100:
                await websocket.close(code=1008, reason="Too many connections for this task")
                return
            self.active_connections[task_id].append(websocket)

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.active_connections.get(task_id, [])
            if websocket in connections:
                connections.remove(websocket)
                try:
                    await websocket.close()
                except Exception:
                    pass
            if not connections:
                self.active_connections.pop(task_id, None)

    async def broadcast(self, task_id: str, message: str) -> None:
        async with self._lock:
            connections = list(self.active_connections.get(task_id, []))
        to_remove: List[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            await self.disconnect(task_id, ws)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)) -> None:
    task_id = websocket.path_params.get("task_id", "")
    if not task_id:
        await websocket.close(code=1008)
        return

    # FastAPI dependency injection resolves Query param to actual string value
    token_str = str(token) if token else ""
    if not token_str or token_str == "None":
        logger.warning(f"WebSocket missing token for task {task_id}")
        await websocket.close(code=1008, reason="Missing token")
        return

    # URL-decode and strip Bearer prefix
    token_str = urllib.parse.unquote(token_str)
    token_str = token_str.replace("Bearer ", "").replace("bearer ", "").strip()

    # Validate JWT structure (3 dot-separated segments)
    segments = token_str.split(".")
    if len(segments) != 3:
        logger.warning(
            f"WebSocket malformed token for task {task_id}: "
            f"{len(segments)} segments, length={len(token_str)}, "
            f"preview={token_str[:20]}..."
        )
        await websocket.close(code=1008, reason="Malformed token")
        return

    # Validate JWT token before accepting connection
    payload = verify_access_token(token_str)
    if not payload:
        logger.warning(f"WebSocket auth failed for task {task_id}")
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await manager.connect(task_id, websocket)
    logger.info(f"WebSocket connected for task {task_id} by user {payload.get('sub', 'unknown')}")

    subscription_task: asyncio.Task | None = None

    async def _subscribe() -> None:
        backoff = 1.0
        max_backoff = 30.0
        while True:
            try:
                async for event in event_bus.subscribe(f"task:{task_id}"):
                    await manager.broadcast(task_id, event.json())
                    backoff = 1.0  # Reset backoff on successful delivery
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"WebSocket subscription error for task {task_id}: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    try:
        subscription_task = asyncio.create_task(_subscribe())
        while True:
            # Keep the connection alive and handle incoming client messages
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data.strip().lower() == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_text("ping")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.warning(f"WebSocket error for task {task_id}: {e}")
    finally:
        if subscription_task is not None:
            subscription_task.cancel()
            try:
                await asyncio.wait_for(subscription_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        await manager.disconnect(task_id, websocket)
