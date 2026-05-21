"""Checkpoint recovery service for resuming tasks from persisted state."""
from typing import Any, Dict, Optional

from ..langgraph.graphs import get_checkpointer
from ..logs.logger import logger


class CheckpointRecoveryService:
    """Loads the latest checkpoint for a task and returns fully restored state.

    Restores:
    - Graph execution state (plan, step index, messages)
    - Tool call history and in-progress tool state
    - Interrupt/approval state for human-in-the-loop
    - Pending writes for incomplete steps
    """

    async def resume_task(self, task_id: str, mode: str, state: dict) -> Optional[Dict[str, Any]]:
        """Attempt to load and reconstruct the last checkpoint for a task.

        Args:
            task_id: The task identifier (used as thread_id in LangGraph).
            mode: Execution mode namespace (task, autonomous, workflow, collaboration).
            state: Current in-memory state (used for merging if needed).

        Returns:
            The fully recovered state dict, or None if no checkpoint exists.
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

            # Restore channel values (graph state)
            recovered_state = dict(checkpoint_tuple.checkpoint.get("channel_values", {}))

            # Restore pending writes (incomplete step outputs, tool results)
            pending_writes = checkpoint_tuple.pending_writes
            if pending_writes:
                recovered_state["pending_writes"] = pending_writes
                logger.info(f"Restored {len(pending_writes)} pending writes for task {task_id}")

            # Restore interrupt/approval state if present
            metadata = checkpoint_tuple.checkpoint.get("metadata", {})
            if metadata.get("interrupt"):
                recovered_state["interrupt"] = metadata["interrupt"]
                logger.info(f"Restored interrupt state for task {task_id}")

            # Ensure critical fields have sensible defaults for resumption
            if "current_step_index" not in recovered_state:
                recovered_state["current_step_index"] = 0
            if "steps" not in recovered_state:
                recovered_state["steps"] = []
            if "tool_calls" not in recovered_state:
                recovered_state["tool_calls"] = []
            if "verified" not in recovered_state:
                recovered_state["verified"] = False
            if "approved" not in recovered_state:
                recovered_state["approved"] = None

            # Merge with any provided in-memory state (e.g., updated query/config)
            if state:
                for key, value in state.items():
                    if value is not None:
                        recovered_state[key] = value

            logger.info(
                f"Recovered checkpoint for task {task_id}: "
                f"step={recovered_state.get('current_step_index')}, "
                f"plan_len={len(recovered_state.get('plan', []))}, "
                f"pending_writes={len(pending_writes) if pending_writes else 0}"
            )
            return recovered_state
        except Exception as e:
            logger.error(f"Checkpoint recovery failed for task {task_id}: {e}")
            return None
