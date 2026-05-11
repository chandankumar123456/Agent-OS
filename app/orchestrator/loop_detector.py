"""Infinite loop detection for task execution.

Detects repeated identical states or actions during task execution
and aborts after a configurable threshold to prevent runaway tasks.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..memory.short_term import redis_client
from ..logs.logger import logger
from .errors import AgentOSError, ErrorCode, ErrorType


class LoopFingerprint(BaseModel):
    """Fingerprint of an execution state for loop detection."""
    task_id: str
    step_number: int = 0
    action: str = ""
    state_hash: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoopDetectionResult(BaseModel):
    """Result of loop detection analysis."""
    loop_detected: bool
    fingerprint: str
    repetition_count: int
    threshold: int
    history: List[str] = Field(default_factory=list)


class InfiniteLoopDetector:
    """Detects infinite loops in task execution.

    Usage:
        detector = InfiniteLoopDetector()
        result = await detector.check(task_id, step=3, action="click_button")
        if result.loop_detected:
            # Abort execution
            pass
    """

    def __init__(
        self,
        redis_prefix: str = "agentos:loop:",
        default_threshold: int = 3,
        history_window: int = 20,
    ):
        self.redis_prefix = redis_prefix
        self.default_threshold = default_threshold
        self.history_window = history_window

    def _history_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}history:{task_id}"

    def _count_key(self, task_id: str, fingerprint: str) -> str:
        return f"{self.redis_prefix}count:{task_id}:{fingerprint}"

    def _compute_fingerprint(
        self,
        task_id: str,
        step_number: int,
        action: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compute a deterministic fingerprint for the current execution state.

        Args:
            task_id: The task identifier.
            step_number: Current step number.
            action: Action being executed.
            state: Optional state dict to include in hash.

        Returns:
            SHA-256 hex digest.
        """
        content = f"{task_id}:{step_number}:{action}"
        if state:
            # Sort keys for determinism
            content += f":{json.dumps(state, sort_keys=True, default=str)}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    async def check(
        self,
        task_id: str,
        step_number: int = 0,
        action: str = "",
        state: Optional[Dict[str, Any]] = None,
        threshold: Optional[int] = None,
    ) -> LoopDetectionResult:
        """Check for infinite loops based on execution fingerprint.

        Args:
            task_id: The task identifier.
            step_number: Current step number.
            action: Action being executed.
            state: Optional state dict.
            threshold: Repetition threshold before loop is declared.

        Returns:
            LoopDetectionResult.
        """
        threshold = threshold or self.default_threshold
        fingerprint = self._compute_fingerprint(task_id, step_number, action, state)
        history_key = self._history_key(task_id)
        count_key = self._count_key(task_id, fingerprint)

        try:
            # Increment count for this fingerprint
            count = await redis_client.client.incr(count_key)
            await redis_client.client.expire(count_key, 3600)

            # Add to history
            entry = json.dumps({
                "fingerprint": fingerprint,
                "step": step_number,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await redis_client.client.lpush(history_key, entry)
            await redis_client.client.ltrim(history_key, 0, self.history_window - 1)
            await redis_client.client.expire(history_key, 3600)

            # Get recent history
            history_entries = await redis_client.client.lrange(
                history_key, 0, self.history_window - 1
            )
            history = []
            for h in history_entries:
                try:
                    data = json.loads(h)
                    history.append(data["fingerprint"])
                except Exception:
                    pass

            loop_detected = count >= threshold

            if loop_detected:
                logger.error(
                    f"Infinite loop detected for task {task_id}",
                    extra={
                        "task_id": task_id,
                        "fingerprint": fingerprint,
                        "repetition_count": count,
                        "threshold": threshold,
                        "action": action,
                        "step": step_number,
                    },
                )

            return LoopDetectionResult(
                loop_detected=loop_detected,
                fingerprint=fingerprint,
                repetition_count=count,
                threshold=threshold,
                history=history,
            )

        except Exception as e:
            logger.error(f"Loop detection failed for {task_id}: {e}")
            # Fail-safe: if we can't detect loops, assume no loop
            return LoopDetectionResult(
                loop_detected=False,
                fingerprint=fingerprint,
                repetition_count=0,
                threshold=threshold,
            )

    async def check_sequence(
        self,
        task_id: str,
        sequence: List[str],
        threshold: int = 2,
    ) -> LoopDetectionResult:
        """Check for repeating sequences of actions.

        Args:
            task_id: The task identifier.
            sequence: List of action identifiers in order.
            threshold: How many times the sequence must repeat.

        Returns:
            LoopDetectionResult.
        """
        sequence_str = ">".join(sequence)
        fingerprint = hashlib.sha256(sequence_str.encode()).hexdigest()[:32]
        count_key = self._count_key(task_id, f"seq:{fingerprint}")

        try:
            count = await redis_client.client.incr(count_key)
            await redis_client.client.expire(count_key, 3600)

            loop_detected = count >= threshold

            if loop_detected:
                logger.error(
                    f"Repeating sequence detected for task {task_id}",
                    extra={
                        "task_id": task_id,
                        "sequence": sequence_str,
                        "repetition_count": count,
                        "threshold": threshold,
                    },
                )

            return LoopDetectionResult(
                loop_detected=loop_detected,
                fingerprint=fingerprint,
                repetition_count=count,
                threshold=threshold,
                history=sequence,
            )
        except Exception as e:
            logger.error(f"Sequence loop detection failed for {task_id}: {e}")
            return LoopDetectionResult(
                loop_detected=False,
                fingerprint=fingerprint,
                repetition_count=0,
                threshold=threshold,
            )

    async def reset(self, task_id: str) -> bool:
        """Reset loop detection state for a task.

        Args:
            task_id: The task identifier.

        Returns:
            True if reset.
        """
        try:
            history_key = self._history_key(task_id)
            await redis_client.client.delete(history_key)

            # Also delete all count keys for this task
            pattern = f"{self.redis_prefix}count:{task_id}:*"
            keys = []
            async for key in redis_client.client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await redis_client.client.delete(*keys)

            logger.info(f"Loop detection reset for {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset loop detection for {task_id}: {e}")
            return False

    async def get_history(self, task_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get execution history for loop analysis.

        Args:
            task_id: The task identifier.
            limit: Maximum history entries.

        Returns:
            List of history entries.
        """
        try:
            entries = await redis_client.client.lrange(
                self._history_key(task_id), 0, limit - 1
            )
            history = []
            for entry in entries:
                try:
                    history.append(json.loads(entry))
                except Exception:
                    pass
            return history
        except Exception as e:
            logger.error(f"Failed to get loop history for {task_id}: {e}")
            return []

    def raise_if_loop(self, result: LoopDetectionResult, task_id: str) -> None:
        """Raise an exception if a loop was detected.

        Args:
            result: LoopDetectionResult.
            task_id: The task identifier.

        Raises:
            AgentOSError: If loop_detected is True.
        """
        if result.loop_detected:
            raise AgentOSError(
                message=(
                    f"Infinite loop detected in task {task_id}: "
                    f"action pattern repeated {result.repetition_count} times "
                    f"(threshold: {result.threshold})"
                ),
                error_type=ErrorType.EXECUTION_ERROR,
                code=ErrorCode.LOOP_DETECTED,
                context={
                    "task_id": task_id,
                    "fingerprint": result.fingerprint,
                    "repetition_count": result.repetition_count,
                    "threshold": result.threshold,
                },
                http_status=500,
            )


# Module-level singleton
loop_detector = InfiniteLoopDetector()
