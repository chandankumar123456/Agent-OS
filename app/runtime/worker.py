import asyncio
from typing import Dict, Any, Optional
from ..agents.base import AgentInput, AgentOutput
from ..logs.logger import logger


class AgentWorker:
    """Async coroutine worker that owns an agent config.

    NOTE (2026-04-27): The inbox queue and _run_loop are FUTURE INFRASTRUCTURE
    for multi-agent message routing. They are currently inactive because:
    - LangGraph bypasses workers and calls tool_registry.execute() directly.
    - Legacy fallback modes call worker.agent_instance.execute() synchronously.
    The loop is started but never receives messages. Do not remove; it will be
    wired back when true multi-agent message passing is implemented.
    """

    def __init__(self, agent_id: str, config: Dict[str, Any], agent_instance):
        self.agent_id = agent_id
        self.config = config
        self.agent_instance = agent_instance
        # FUTURE: inbox queue for multi-agent message routing (currently inactive)
        self.inbox: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._health = {"status": "healthy", "last_heartbeat": None}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"AgentWorker {self.agent_id} started")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"AgentWorker {self.agent_id} stopped")

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute agent directly (synchronous-style call)."""
        try:
            result = await self.agent_instance.execute(input_data)
            self._health["last_heartbeat"] = asyncio.get_event_loop().time()
            return result
        except Exception as e:
            logger.error(f"AgentWorker {self.agent_id} execution error: {e}")
            from ..agents.base import AgentStatus
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="execution_error",
                error_message=str(e),
                recoverable=True,
            )

    async def on_message(self, message):
        """Handle incoming MCP message by placing it in the inbox queue."""
        logger.info(f"AgentWorker {self.agent_id} received message: {getattr(message, 'message_id', 'unknown')}")
        await self.inbox.put(message)

    async def health(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self._health["status"],
            "running": self._running,
            "config": self.config,
        }

    async def _run_loop(self):
        """Main loop that processes inbox messages."""
        while self._running:
            try:
                message = await asyncio.wait_for(self.inbox.get(), timeout=1.0)
                await self._process_message(message)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"AgentWorker {self.agent_id} loop error: {e}")

    async def _process_message(self, message):
        """Process a single message from the inbox."""
        try:
            payload = getattr(message, 'payload', None)
            if payload and hasattr(payload, 'input_data'):
                input_data = payload.input_data
                if isinstance(input_data, dict):
                    from ..agents.base import AgentInput, AgentRole
                    from uuid import UUID
                    task_id_raw = getattr(message, 'task_id', None)
                    step_id_raw = getattr(message, 'step_id', None)
                    # Validate UUIDs
                    try:
                        task_id = UUID(str(task_id_raw)) if task_id_raw else UUID(int=0)
                        step_id = UUID(str(step_id_raw)) if step_id_raw else UUID(int=0)
                    except (ValueError, TypeError) as uuid_err:
                        logger.error(f"AgentWorker {self.agent_id} received invalid UUIDs: {uuid_err}")
                        return
                    agent_input = AgentInput(
                        task_id=task_id,
                        step_id=step_id,
                        role=AgentRole(self.config.get("role", "executor").upper()),
                        input_data=input_data,
                        context={},
                    )
                    result = await asyncio.wait_for(self.execute(agent_input), timeout=300)
                    logger.info(f"AgentWorker {self.agent_id} processed message with status: {result.status}")
            else:
                logger.warning(f"AgentWorker {self.agent_id} dropped message with missing payload or input_data")
        except asyncio.TimeoutError:
            logger.error(f"AgentWorker {self.agent_id} timed out processing message")
        except Exception as e:
            logger.error(f"AgentWorker {self.agent_id} failed to process message: {e}")
