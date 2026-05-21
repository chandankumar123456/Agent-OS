from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ...orchestrator.event_bus import event_bus
from ...logs.logger import logger

router = APIRouter(prefix="/tasks", tags=["events"])


@router.get("/{task_id}/events")
async def task_events(task_id: str, request: Request) -> StreamingResponse:
    async def event_stream():
        try:
            async for event in event_bus.subscribe(f"task:{task_id}"):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield f"event: {event.event_type}\ndata: {event.json()}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error for task {task_id}: {e}")
        finally:
            logger.info(f"SSE stream closed for task {task_id}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
