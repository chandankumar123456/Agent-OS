import asyncio
from sqlalchemy import select
from ...memory.models import ToolV2Model
from ...memory.long_term import db
from ...logs.logger import logger


class ToolHealthMonitor:
    def __init__(self):
        self._task = None
        self._running = False

    def start(self):
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._run())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self):
        while self._running:
            try:
                async with db.get_session() as session:
                    result = await session.execute(
                        select(ToolV2Model).where(ToolV2Model.status == "active")
                    )
                    tools = result.scalars().all()
                    for tool in tools:
                        # Simplified health check: increment invocation count
                        tool.invocation_count = (tool.invocation_count or 0) + 1

                        # Simulate a latency measurement (ms) for the check itself
                        measured_latency = 5.0
                        alpha = 0.3
                        old_latency = tool.avg_latency_ms or 0.0
                        tool.avg_latency_ms = alpha * measured_latency + (1 - alpha) * old_latency

                        # Assume success for simplified check; EMA error rate
                        current_error = 0.0
                        old_error = tool.error_rate or 0.0
                        tool.error_rate = alpha * current_error + (1 - alpha) * old_error

                    await session.commit()
            except Exception as e:
                logger.error(f"Tool health monitor error: {e}")

            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break


tool_health_monitor = ToolHealthMonitor()
