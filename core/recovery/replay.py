"""Execution replay service for deterministic replay from checkpoints.

Reconstructs task execution from stored checkpoints and traces,
validates replay fidelity, and detects divergences.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..memory.long_term import db
from ..logs.logger import logger


class ReplayStep(BaseModel):
    """A single replayed step."""
    step_index: int
    node_name: str
    input_state: Dict[str, Any] = Field(default_factory=dict)
    output_state: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None
    divergence_detected: bool = Field(default=False)
    divergence_details: Optional[str] = None


class ReplayResult(BaseModel):
    """Result of an execution replay."""
    replay_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    success: bool = Field(default=False)
    replay_log: List[ReplayStep] = Field(default_factory=list)
    final_state: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = Field(default=0.0)
    divergence_count: int = Field(default=0)
    from_checkpoint: Optional[str] = None


class ExecutionReplayService:
    """Replays task executions from stored checkpoints and traces.

    Loads checkpoint chain from PostgreSQL, reconstructs execution steps,
    and optionally validates against recorded traces for divergence.

    Usage:
        replay = ExecutionReplayService()
        result = await replay.replay(task_id, from_checkpoint="checkpoint-123")
    """

    def __init__(self, redis_prefix: str = "agentos:replay:"):
        self.redis_prefix = redis_prefix

    def _redis_key(self, replay_id: str) -> str:
        return f"{self.redis_prefix}{replay_id}"

    async def replay(
        self,
        task_id: str,
        from_checkpoint: Optional[str] = None,
        validate_against_traces: bool = True,
    ) -> ReplayResult:
        """Replay a task execution.

        Args:
            task_id: The task identifier.
            from_checkpoint: Optional checkpoint ID to start from.
            validate_against_traces: Whether to validate against recorded traces.

        Returns:
            ReplayResult with replay log and divergence info.
        """
        start_time = datetime.now(timezone.utc)
        replay_id = str(uuid4())
        result = ReplayResult(
            replay_id=replay_id,
            task_id=task_id,
            from_checkpoint=from_checkpoint,
        )

        # Load checkpoints
        checkpoints = await self._load_checkpoints(task_id, from_checkpoint)
        if not checkpoints:
            logger.warning(f"No checkpoints found for task {task_id}")
            result.success = False
            return result

        # Load traces for validation
        traces = []
        if validate_against_traces:
            traces = await self._load_traces(task_id)

        # Replay steps
        step_index = 0
        for checkpoint in checkpoints:
            step = ReplayStep(
                step_index=step_index,
                node_name=checkpoint.get("node_name", "unknown"),
                input_state=checkpoint.get("input_state", {}),
                output_state=checkpoint.get("output_state", {}),
                timestamp=checkpoint.get("timestamp"),
            )

            # Validate against trace if available
            if validate_against_traces and step_index < len(traces):
                trace = traces[step_index]
                divergence = self._detect_divergence(step, trace)
                if divergence:
                    step.divergence_detected = True
                    step.divergence_details = divergence
                    result.divergence_count += 1

            result.replay_log.append(step)
            result.final_state = step.output_state
            step_index += 1

        duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        result.duration_ms = round(duration, 2)
        result.success = result.divergence_count == 0

        # Cache result in Redis
        await self._cache_replay_result(result)

        logger.info(
            f"Replayed task {task_id}: {len(result.replay_log)} steps, "
            f"{result.divergence_count} divergences, success={result.success}"
        )
        return result

    async def get_replay_result(self, replay_id: str) -> Optional[ReplayResult]:
        """Retrieve a cached replay result.

        Args:
            replay_id: The replay identifier.

        Returns:
            ReplayResult if found, None otherwise.
        """
        try:
            data = await redis_client.get(self._redis_key(replay_id))
            if data:
                return ReplayResult(**data)
        except Exception as e:
            logger.warning(f"Redis replay read failed for {replay_id}: {e}")
        return None

    async def list_replays_for_task(self, task_id: str) -> List[str]:
        """List replay IDs for a task.

        Args:
            task_id: The task identifier.

        Returns:
            List of replay IDs.
        """
        # This is a simplified implementation; in production use Redis scan or DB query
        return []

    async def _load_checkpoints(
        self,
        task_id: str,
        from_checkpoint: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load checkpoint chain from PostgreSQL."""
        checkpoints: List[Dict[str, Any]] = []
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import CheckpointModel
                query = (
                    select(CheckpointModel)
                    .where(CheckpointModel.thread_id == task_id)
                    .order_by(CheckpointModel.created_at)
                )
                result = await session.execute(query)
                rows = result.scalars().all()

                started = from_checkpoint is None
                for row in rows:
                    if not started:
                        if row.checkpoint_id == from_checkpoint:
                            started = True
                        else:
                            continue

                    try:
                        import json
                        checkpoint_data = json.loads(row.checkpoint) if isinstance(row.checkpoint, str) else row.checkpoint
                        checkpoints.append({
                            "checkpoint_id": row.checkpoint_id,
                            "node_name": checkpoint_data.get("node_name", "unknown"),
                            "input_state": checkpoint_data.get("input_state", {}),
                            "output_state": checkpoint_data.get("output_state", {}),
                            "timestamp": row.created_at.isoformat() if row.created_at else None,
                        })
                    except Exception as e:
                        logger.warning(f"Failed to parse checkpoint {row.checkpoint_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to load checkpoints for {task_id}: {e}")
        return checkpoints

    async def _load_traces(self, task_id: str) -> List[Dict[str, Any]]:
        """Load recorded traces from PostgreSQL."""
        traces: List[Dict[str, Any]] = []
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import NodeTraceModel
                result = await session.execute(
                    select(NodeTraceModel)
                    .where(NodeTraceModel.task_id == task_id)
                    .order_by(NodeTraceModel.created_at)
                )
                rows = result.scalars().all()
                for row in rows:
                    traces.append({
                        "node_id": row.node_id,
                        "input_data": row.input_data or {},
                        "output_data": row.output_data or {},
                        "status": row.status,
                    })
        except Exception as e:
            logger.warning(f"Failed to load traces for {task_id}: {e}")
        return traces

    def _detect_divergence(
        self,
        step: ReplayStep,
        trace: Dict[str, Any],
    ) -> Optional[str]:
        """Detect divergence between replayed step and recorded trace.

        Args:
            step: Replayed step.
            trace: Recorded trace.

        Returns:
            Divergence description if found, None otherwise.
        """
        # Simple structural comparison of output state vs trace output
        trace_output = trace.get("output_data", {})
        step_output = step.output_state

        # Compare key fields that should match
        if isinstance(trace_output, dict) and isinstance(step_output, dict):
            for key in ["status", "result", "error"]:
                if key in trace_output and key in step_output:
                    if trace_output[key] != step_output[key]:
                        return f"Field '{key}' mismatch: trace={trace_output[key]}, replay={step_output[key]}"
        return None

    async def _cache_replay_result(self, result: ReplayResult) -> None:
        """Cache replay result in Redis."""
        try:
            await redis_client.set(
                self._redis_key(result.replay_id),
                result.model_dump(mode="json"),
                expire=86400,
            )
        except Exception as e:
            logger.warning(f"Redis replay cache failed: {e}")


# Module-level singleton
execution_replay = ExecutionReplayService()
