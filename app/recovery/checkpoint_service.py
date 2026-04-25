"""Checkpoint recovery service for resuming tasks from persisted state."""
from typing import Any, Dict, Optional

from ..langgraph.graphs import get_checkpointer
from ..logs.logger import logger


class CheckpointRecoveryService:
    """Loads the latest checkpoint for a task and returns the recovered state."""

    async def resume_task(self, task_id: str, mode: str, state: dict) -> Optional[Dict[str, Any]]:
        """Attempt to load the last checkpoint for a task.

        Args:
            task_id: The task identifier (used as thread_id in LangGraph).
            mode: Execution mode namespace (task, autonomous, workflow, collaboration).
            state: Current in-memory state (used for merging if needed).

        Returns:
            The recovered checkpoint channel_values/state, or None if no checkpoint exists.
        """
        checkpointer = get_checkpointer()
        logger.info(f"Resuming task {task_id} from checkpoint")
        config = {
            "configurable": {
                "thread_id": task_id,
                "checkpoint_ns": mode,
            }
        }
        try:
            checkpoint_tuple = await checkpointer.aget_tuple(config)
            if checkpoint_tuple is None:
                logger.info(f"No checkpoint found for task {task_id} mode {mode}")
                return None
            recovered_state = checkpoint_tuple.checkpoint.get("channel_values", {})
            logger.info(f"Recovered checkpoint for task {task_id}")
            return recovered_state
        except Exception as e:
            logger.error(f"Checkpoint recovery failed for task {task_id}: {e}")
            return None
