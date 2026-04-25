"""Recovery Engine — decides what to do when execution fails."""
from typing import Dict, Any, Optional, List

from .models import RecoveryAction, RecoveryDecision, VerificationReport, VerificationResult
from ..logs.logger import logger
from ..memory.short_term import redis_client


class RecoveryEngine:
    """Analyzes failures and decides recovery actions.

    Actions:
    - RETRY: transient failure, try again
    - REPLAN: plan was wrong, generate new plan
    - SWITCH_TOOL: tool failed, try alternative
    - ESCALATE: unrecoverable, needs human attention
    - SKIP: non-critical step, continue without it
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._tool_alternatives: Dict[str, List[str]] = {
            "filesystem__write_file": ["shell__execute_command"],
            "shell__execute_command": ["filesystem__write_file"],
            "browser__scrape_page": ["browser__http_request"],
            "browser__http_request": ["browser__scrape_page"],
        }

    def _retry_key(self, task_id: str, step_id: Optional[str]) -> str:
        return f"agentos:recovery:{task_id}:{step_id or 'task'}"

    async def _get_retry_count(self, task_id: str, step_id: Optional[str]) -> int:
        if not redis_client.client:
            raise RuntimeError("Redis client is unavailable")
        key = self._retry_key(task_id, step_id)
        value = await redis_client.client.get(key)
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    async def _increment_retry(self, task_id: str, step_id: Optional[str]) -> int:
        if not redis_client.client:
            raise RuntimeError("Redis client is unavailable")
        key = self._retry_key(task_id, step_id)
        new_count = await redis_client.client.incr(key)
        await redis_client.client.expire(key, 604800)
        return new_count

    async def reset_retries(self, task_id: str) -> None:
        """Clear retry counts for a task."""
        if not redis_client.client:
            raise RuntimeError("Redis client is unavailable")
        pattern = f"agentos:recovery:{task_id}:*"
        keys = []
        async for key in redis_client.client.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await redis_client.client.delete(*keys)
            logger.info(f"Reset retry counts for task {task_id} ({len(keys)} keys)")

    async def decide(
        self,
        task_id: str,
        step_id: Optional[str],
        error: Optional[str],
        verification_report: Optional[VerificationReport] = None,
        current_tool: Optional[str] = None,
    ) -> RecoveryDecision:
        """Decide the recovery action for a failure."""
        current_retries = await self._get_retry_count(task_id, step_id)

        # Check if max retries reached
        if current_retries >= self.max_retries:
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action=RecoveryAction.ESCALATE,
                reason=f"Max retries ({self.max_retries}) exceeded",
                max_retries_reached=True,
                escalation_reason=error or "Repeated failures",
            )

        # Verification-driven recovery
        if verification_report:
            if verification_report.retry_suggested:
                await self._increment_retry(task_id, step_id)
                return RecoveryDecision(
                    task_id=task_id,
                    step_id=step_id,
                    action=RecoveryAction.RETRY,
                    reason=f"Verification failed but retryable: {verification_report.failure_reason}",
                )
            if verification_report.result == VerificationResult.FAIL:
                # Try switching tool if available
                alt = self._get_alternative_tool(current_tool)
                if alt:
                    return RecoveryDecision(
                        task_id=task_id,
                        step_id=step_id,
                        action=RecoveryAction.SWITCH_TOOL,
                        reason=f"Verification failed, trying alternative tool: {alt}",
                        next_tool=alt,
                    )
                # Otherwise replan
                return RecoveryDecision(
                    task_id=task_id,
                    step_id=step_id,
                    action=RecoveryAction.REPLAN,
                    reason="Verification failed and no alternative tool available",
                )

        # Error-pattern-based recovery
        if error:
            error_lower = error.lower()

            # Transient errors → retry
            transient_patterns = [
                "timeout", "connection", "temporarily", "rate limit",
                "503", "502", "504", "429", "reset", "refused",
            ]
            if any(p in error_lower for p in transient_patterns):
                await self._increment_retry(task_id, step_id)
                return RecoveryDecision(
                    task_id=task_id,
                    step_id=step_id,
                    action=RecoveryAction.RETRY,
                    reason=f"Transient error detected: {error}",
                )

            # Tool not found → replan
            if "tool not found" in error_lower or "not found" in error_lower:
                return RecoveryDecision(
                    task_id=task_id,
                    step_id=step_id,
                    action=RecoveryAction.REPLAN,
                    reason="Required tool not available",
                )

            # Permission denied → escalate
            if "permission" in error_lower or "unauthorized" in error_lower or "access denied" in error_lower:
                return RecoveryDecision(
                    task_id=task_id,
                    step_id=step_id,
                    action=RecoveryAction.ESCALATE,
                    reason="Permission denied — requires human intervention",
                    escalation_reason=error,
                )

            # Tool execution error → try alternative or retry
            alt = self._get_alternative_tool(current_tool)
            if alt:
                return RecoveryDecision(
                    task_id=task_id,
                    step_id=step_id,
                    action=RecoveryAction.SWITCH_TOOL,
                    reason=f"Tool error, switching to alternative: {alt}",
                    next_tool=alt,
                )

        # Default: retry once, then escalate
        if current_retries < self.max_retries:
            await self._increment_retry(task_id, step_id)
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action=RecoveryAction.RETRY,
                reason=f"Retrying after failure: {error or 'unknown error'}",
            )

        return RecoveryDecision(
            task_id=task_id,
            step_id=step_id,
            action=RecoveryAction.ESCALATE,
            reason="Unrecoverable failure after retries",
            escalation_reason=error or "Unknown error",
        )

    def _get_alternative_tool(self, tool_name: Optional[str]) -> Optional[str]:
        if not tool_name:
            return None
        alternatives = self._tool_alternatives.get(tool_name, [])
        return alternatives[0] if alternatives else None


# Global singleton
recovery_engine = RecoveryEngine()
