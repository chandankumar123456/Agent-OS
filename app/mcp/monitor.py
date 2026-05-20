from __future__ import annotations
import asyncio
from typing import Dict

from .registry import mcp_registry
from ..memory.long_term import mcp_server_repo
from ..logs.logger import logger


class MCPHealthMonitor:
    """Periodic background health monitor for MCP servers."""

    def __init__(self, interval_seconds: int = 60):
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._failure_counts: Dict[str, int] = {}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("MCP health monitor started")

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            logger.info("MCP health monitor stopped")
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._run_checks()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"MCP health monitor loop error: {e}")
            await asyncio.sleep(self.interval_seconds)

    async def _run_checks(self) -> None:
        servers = await mcp_registry.list_all()
        for server in servers:
            name = server["name"]
            try:
                status = await mcp_registry.health_check(name)
                if status == "unhealthy":
                    self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
                    if self._failure_counts[name] >= 3:
                        # Auto-disable after 3 consecutive failures
                        if server.get("status") != "inactive":
                            await mcp_server_repo.update(server_id=server["id"], status="inactive")
                            logger.warning(f"MCP server {name} auto-disabled after 3 consecutive failures")
                        self._failure_counts[name] = 0
                else:
                    # Reset failure count on any non-unhealthy status
                    self._failure_counts[name] = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Health check failed for MCP server {name}: {e}")


mcp_health_monitor = MCPHealthMonitor()
