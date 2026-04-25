import asyncio
from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect
from ..orchestrator.v2.event_bus import event_bus, Event
from ..logs.logger import logger


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        connections = self.active_connections.get(task_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(task_id, None)

    async def broadcast(self, task_id: str, message: str) -> None:
        connections = self.active_connections.get(task_id, [])
        to_remove: List[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(task_id, ws)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    task_id = websocket.path_params.get("task_id", "")
    if not task_id:
        await websocket.close(code=1008)
        return
    await manager.connect(task_id, websocket)
    logger.info(f"WebSocket connected for task {task_id}")

    subscription_task: asyncio.Task | None = None

    async def _subscribe() -> None:
        try:
            async for event in event_bus.subscribe(f"task:{task_id}"):
                await manager.broadcast(task_id, event.json())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"WebSocket subscription error for task {task_id}: {e}")

    try:
        subscription_task = asyncio.create_task(_subscribe())
        while True:
            # Keep the connection alive and handle incoming client messages
            data = await websocket.receive_text()
            # Echo back or handle ping/pong if needed
            if data.strip().lower() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.warning(f"WebSocket error for task {task_id}: {e}")
    finally:
        if subscription_task is not None:
            subscription_task.cancel()
            try:
                await subscription_task
            except asyncio.CancelledError:
                pass
        manager.disconnect(task_id, websocket)
