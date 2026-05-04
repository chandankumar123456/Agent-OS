"""Recovery Engine — decides what to do when execution fails."""
from enum import Enum, auto
from typing import Dict, Any, Optional, List

from .models import (
    RecoveryAction,
    RecoveryDecision,
    VerificationReport,
    VerificationResult,
    ExecutionEnvironment,
)
from ..logs.logger import logger
from ..memory.short_term import redis_client


class RecoveryStrategy(Enum):
    """Strategy for recovery — constrains what fallback environments/tools are allowed.

    - GENERIC: No constraints; use any fallback environment or tool.
    - DESKTOP: Stay within desktop tools/environments; never fall back to browser or shell.
    - BROWSER: Stay within browser tools/environments.
    - SHELL: Stay within shell tools/environments.
    """
    GENERIC = auto()
    DESKTOP = auto()
    BROWSER = auto()
    SHELL = auto()


class DesktopRecoveryAction(Enum):
    """Desktop-specific positive recovery action classifications.

    These are mapped to RecoveryDecision (via SWITCH_TOOL / ESCALATE) by
    DesktopRecoveryPlanner.
    """
    REFOCUS = auto()           # → SWITCH_TOOL: desktop_env__ensure_focus
    REBUILD_TREE = auto()      # → SWITCH_TOOL: desktop__get_ui_tree
    DISMISS_POPUP = auto()     # → SWITCH_TOOL: desktop_env__press_key {"key": "esc"}
    VISION_ESCALATE = auto()   # → SWITCH_TOOL: desktop_env__screenshot
    ESCALATE = auto()          # → ESCALATE: unrecoverable


class DesktopRecoveryPlanner:
    """Plans positive desktop recovery strategies based on error patterns.

    Returns a RecoveryDecision that the RecoveryEngine can execute directly,
    using SWITCH_TOOL to a concrete recovery tool or ESCALATE when no
    positive strategy matches.
    """

    def plan(
        self,
        error: Optional[str],
        current_tool: Optional[str],
        task_id: str,
    ) -> RecoveryDecision:
        """Analyse error message and produce a desktop recovery decision.

        Args:
            error: The error message, if any.
            current_tool: The tool that failed, if known.
            task_id: The task identifier.

        Returns:
            A RecoveryDecision with SWITCH_TOOL to a concrete recovery tool,
            or ESCALATE if no positive match is found.
        """
        if not error:
            return RecoveryDecision(
                task_id=task_id,
                action=RecoveryAction.ESCALATE,
                reason="Desktop recovery planner: no error provided, escalating for human review",
            )

        error_lower = error.lower()

        # Focus / foreground / activation issues → re-focus the window
        if any(p in error_lower for p in ("focus", "foreground", "not active", "hwnd")):
            return RecoveryDecision(
                task_id=task_id,
                action=RecoveryAction.SWITCH_TOOL,
                reason=f"Desktop recovery: focus/activation error detected, switching to ensure_focus",
                next_tool="desktop_env__ensure_focus",
            )

        # Stale element / tree changed → rebuild the UI tree
        if any(p in error_lower for p in ("stale", "element not found", "tree changed", "invalid element")):
            return RecoveryDecision(
                task_id=task_id,
                action=RecoveryAction.SWITCH_TOOL,
                reason=f"Desktop recovery: stale UI element detected, rebuilding UI tree",
                next_tool="desktop__get_ui_tree",
            )

        # Popup / dialog / modal blocking → dismiss with Esc
        if any(p in error_lower for p in ("popup", "dialog", "modal", "blocking")):
            return RecoveryDecision(
                task_id=task_id,
                action=RecoveryAction.SWITCH_TOOL,
                reason=f"Desktop recovery: popup/dialog blocking, pressing Esc to dismiss",
                next_tool="desktop_env__press_key",
            )

        # Coordinate / pyautogui / vision / click / type failure → screenshot for visual inspection
        if any(p in error_lower for p in ("pyautogui", "coordinate", "click failed", "type failed", "vision")):
            return RecoveryDecision(
                task_id=task_id,
                action=RecoveryAction.SWITCH_TOOL,
                reason=f"Desktop recovery: coordinate/vision failure, taking screenshot for visual analysis",
                next_tool="desktop_env__screenshot",
            )

        # No positive match — fall through to the engine's generic logic
        return RecoveryDecision(
            task_id=task_id,
            action=RecoveryAction.ESCALATE,
            reason="Desktop recovery planner: no positive match for error pattern",
        )


class RecoveryEngine:
    """Analyzes failures and decides recovery actions.

    Actions:
    - RETRY: transient failure, try again
    - REPLAN: plan was wrong, generate new plan
    - SWITCH_TOOL: tool failed, try alternative
    - SWITCH_ENVIRONMENT: environment failure, try fallback environment
    - ESCALATE: unrecoverable, needs human attention
    - SKIP: non-critical step, continue without it
    """

    # Mapping of environment to ordered list of fallback environments.
    ENVIRONMENT_FALLBACKS: Dict[ExecutionEnvironment, List[ExecutionEnvironment]] = {
        ExecutionEnvironment.DESKTOP: [
            ExecutionEnvironment.BROWSER_UI,
            ExecutionEnvironment.CLOUD_API,
            ExecutionEnvironment.SHELL,
        ],
        ExecutionEnvironment.BROWSER_UI: [
            ExecutionEnvironment.CLOUD_API,
            ExecutionEnvironment.SHELL,
            ExecutionEnvironment.LOCAL,
        ],
        ExecutionEnvironment.CLOUD_API: [
            ExecutionEnvironment.SHELL,
            ExecutionEnvironment.LOCAL,
        ],
        ExecutionEnvironment.SHELL: [
            ExecutionEnvironment.LOCAL,
        ],
        ExecutionEnvironment.LOCAL: [
            ExecutionEnvironment.SHELL,
        ],
        ExecutionEnvironment.FILE: [
            ExecutionEnvironment.SHELL,
        ],
        ExecutionEnvironment.SANDBOX: [
            ExecutionEnvironment.SHELL,
        ],
    }

    # Environment-specific error substrings that trigger a fallback.
    _ENV_ERROR_PATTERNS: Dict[ExecutionEnvironment, List[str]] = {
        ExecutionEnvironment.BROWSER_UI: ["playwright_timeout"],
        ExecutionEnvironment.DESKTOP: ["pyautogui_fail", "display_not_found"],
        ExecutionEnvironment.SHELL: ["permission_denied"],
        ExecutionEnvironment.CLOUD_API: ["network_unreachable"],
    }

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._memory_retry_counts: Dict[str, int] = {}
        self._tool_alternatives: Dict[str, List[str]] = {
            "filesystem__write_file": ["shell__execute_command"],
            "shell__execute_command": ["filesystem__write_file"],
            "browser__scrape_page": ["browser__http_request", "cloud_api__scrape_page"],
            "browser__http_request": ["browser__scrape_page", "cloud_api__http_request"],
            "browser__search": ["cloud_api__search"],
            "cloud_api__search": ["browser__search"],
            # FR6.1: Desktop tools must fall back to other desktop tools, NOT browser/shell
            # Only tools registered in the tool registry are mapped; phantom tools
            # (desktop__screenshot, desktop__click, desktop__type) are removed.
            "desktop__get_ui_tree": ["desktop_env__screenshot"],
            "desktop__click_element": ["desktop__focus_and_interact"],
            "desktop__type_element": ["desktop__focus_and_interact", "desktop_env__type_text"],
            "desktop__focus_and_interact": ["desktop__click_element", "desktop__type_element"],
            "desktop_env__screenshot": ["desktop__get_ui_tree"],
            "desktop_env__click": ["desktop_env__press_key", "desktop__click_element"],
            "desktop_env__type_text": ["desktop__type_element", "desktop_env__press_key"],
            "desktop_env__focus_window": ["desktop_env__ensure_focus"],
            "desktop_env__ensure_focus": ["desktop_env__focus_window"],
            "desktop_env__press_key": ["desktop_env__type_text"],
            "cloud_api__scrape_page": ["browser__scrape_page"],
            "cloud_api__http_request": ["browser__http_request"],
        }

    def _retry_key(self, task_id: str, step_id: Optional[str]) -> str:
        return f"agentos:recovery:{task_id}:{step_id or 'task'}"

    async def _get_retry_count(self, task_id: str, step_id: Optional[str]) -> int:
        if not redis_client.client:
            logger.debug(f"Redis unavailable; using in-memory retry count for {task_id}")
            return self._memory_retry_counts.get(self._retry_key(task_id, step_id), 0)
        key = self._retry_key(task_id, step_id)
        value = await redis_client.client.get(key)
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    async def _increment_retry(
        self,
        task_id: str,
        step_id: Optional[str],
        recovery_strategy: Optional[RecoveryStrategy] = None,
    ) -> int:
        key = self._retry_key(task_id, step_id)
        if not redis_client.client:
            logger.debug(f"Redis unavailable; incrementing in-memory retry count for {task_id}")
            self._memory_retry_counts[key] = self._memory_retry_counts.get(key, 0) + 1
            return self._memory_retry_counts[key]
        new_count = await redis_client.client.incr(key)
        # FR6.5: Desktop tasks use a short 1-hour TTL so stale retry counters
        # don't persist across task restarts.  Generic tasks keep the 7-day default.
        ttl = 3600 if recovery_strategy == RecoveryStrategy.DESKTOP else 604800
        await redis_client.client.expire(key, ttl)
        return new_count

    async def reset_retries(self, task_id: str) -> None:
        """Clear retry counts for a task."""
        # Clear in-memory counts
        prefix = f"agentos:recovery:{task_id}:"
        for k in list(self._memory_retry_counts.keys()):
            if k.startswith(prefix):
                del self._memory_retry_counts[k]
        if not redis_client.client:
            logger.debug(f"Redis unavailable; cleared in-memory retry counts for {task_id}")
            return
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
        current_environment: Optional[ExecutionEnvironment] = None,
        execution_state: Optional[Dict[str, Any]] = None,
        recovery_strategy: Optional[RecoveryStrategy] = None,
    ) -> RecoveryDecision:
        """Decide the recovery action for a failure.

        Args:
            task_id: The task identifier.
            step_id: Optional step identifier.
            error: The error message, if any.
            verification_report: Optional verification report.
            current_tool: The tool that failed, if known.
            current_environment: The execution environment that failed, if known.
            execution_state: Optional canonical execution state.
            recovery_strategy: Optional strategy constraining fallback options
                (e.g., RecoveryStrategy.DESKTOP prevents falling back to browser/shell).
        """
        # If canonical execution state shows terminal success, do NOT recover
        if execution_state:
            from ..execution_state import ExecutionState, ExecutionVerdict
            state = ExecutionState.from_dict(execution_state)
            # Find the current step from step_id or check any terminal success
            for step_rec in state.steps.values():
                if step_rec.has_terminal_success:
                    logger.info(
                        f"[RecoveryEngine] Terminal success exists for step {step_rec.step_number}; "
                        f"skipping recovery."
                    )
                    return RecoveryDecision(
                        task_id=task_id,
                        step_id=step_id,
                        action=RecoveryAction.SKIP,
                        reason="Terminal success already recorded in canonical execution state",
                    )

        # FR6.2: For DESKTOP strategy, run positive recovery planner first.
        # If it produces a concrete recovery action (non-ESCALATE), return it
        # immediately — no need to count retries for a recovery tool switch.
        if recovery_strategy == RecoveryStrategy.DESKTOP and error:
            planner_decision = DesktopRecoveryPlanner().plan(error=error, current_tool=current_tool, task_id=task_id)
            if planner_decision.action != RecoveryAction.ESCALATE:
                logger.info(
                    f"[RecoveryEngine] DesktopRecoveryPlanner produced positive action: "
                    f"{planner_decision.action.value} → {planner_decision.next_tool}"
                )
                return planner_decision
            # Planner returned ESCALATE (no positive match) — fall through to generic logic

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
                await self._increment_retry(task_id, step_id, recovery_strategy)
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

            # Environment-specific failures → switch environment (checked before generic transient retry)
            if current_environment:
                fallback = self._suggest_environment_fallback(current_environment, error_lower)
                if fallback:
                    # FR6.1: DESKTOP strategy must not fall back to browser/shell environments
                    if recovery_strategy == RecoveryStrategy.DESKTOP:
                        if fallback in (ExecutionEnvironment.BROWSER_UI, ExecutionEnvironment.CLOUD_API, ExecutionEnvironment.SHELL):
                            # Try a desktop tool alternative instead of switching to non-desktop env
                            alt = self._get_alternative_tool(current_tool)
                            if alt:
                                return RecoveryDecision(
                                    task_id=task_id,
                                    step_id=step_id,
                                    action=RecoveryAction.SWITCH_TOOL,
                                    reason=(
                                        f"Desktop env failure ({error}) — DESKTOP strategy prevents "
                                        f"env fallback to {fallback.value}; trying alternative tool: {alt}"
                                    ),
                                    next_tool=alt,
                                )
                            # No desktop alternative — escalate
                            return RecoveryDecision(
                                task_id=task_id,
                                step_id=step_id,
                                action=RecoveryAction.ESCALATE,
                                reason=(
                                    f"Desktop env failure ({error}) — DESKTOP strategy prevents "
                                    f"env fallback to {fallback.value}; no desktop alternative available"
                                ),
                                escalation_reason=error,
                            )
                    return RecoveryDecision(
                        task_id=task_id,
                        step_id=step_id,
                        action=RecoveryAction.SWITCH_ENVIRONMENT,
                        reason=(
                            f"{current_environment.value} environment failure detected ({error}), "
                            f"switching to {fallback.value}"
                        ),
                        next_environment=fallback,
                    )

            # Transient errors → retry
            transient_patterns = [
                "timeout", "connection", "temporarily", "rate limit",
                "503", "502", "504", "429", "reset", "refused",
                "playwright_timeout", "network_unreachable",
            ]
            if any(p in error_lower for p in transient_patterns):
                await self._increment_retry(task_id, step_id, recovery_strategy)
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
            await self._increment_retry(task_id, step_id, recovery_strategy)
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

    def _suggest_environment_fallback(
        self,
        current_environment: ExecutionEnvironment,
        error_lower: str,
    ) -> Optional[ExecutionEnvironment]:
        """Return the next fallback environment if the error is environment-specific."""
        patterns = self._ENV_ERROR_PATTERNS.get(current_environment, [])
        if not any(p in error_lower for p in patterns):
            return None
        fallbacks = self.ENVIRONMENT_FALLBACKS.get(current_environment, [])
        return fallbacks[0] if fallbacks else None

    async def execute(
        self,
        decision: RecoveryDecision,
        recovery_strategy: Optional[RecoveryStrategy] = None,
    ) -> RecoveryDecision:
        """Execute (validate/enforce) a recovery decision, respecting the recovery strategy.

        For RecoveryStrategy.DESKTOP:
        - Rejects SWITCH_ENVIRONMENT to browser/shell/cloud environments.
        - Rejects SWITCH_TOOL to non-desktop tools (browser, shell, cloud_api).
        - Falls back to escalation when no desktop-appropriate recovery is available.

        For other strategies, the decision passes through unchanged.

        Args:
            decision: The recovery decision to execute/validate.
            recovery_strategy: The strategy constraining allowed recovery actions.

        Returns:
            A potentially modified RecoveryDecision that respects the strategy.
        """
        if recovery_strategy != RecoveryStrategy.DESKTOP:
            return decision

        # FR6.1: DESKTOP strategy — enforce desktop-only recovery actions

        # Reject environment switches to non-desktop environments
        if decision.action == RecoveryAction.SWITCH_ENVIRONMENT:
            if decision.next_environment in (
                ExecutionEnvironment.BROWSER_UI,
                ExecutionEnvironment.CLOUD_API,
                ExecutionEnvironment.SHELL,
            ):
                logger.warning(
                    f"RecoveryEngine.execute: DESKTOP strategy overrides "
                    f"SWITCH_ENVIRONMENT to {decision.next_environment.value}; "
                    f"escalating instead."
                )
                return RecoveryDecision(
                    task_id=decision.task_id,
                    step_id=decision.step_id,
                    action=RecoveryAction.ESCALATE,
                    reason=(
                        f"DESKTOP strategy prevented switch to "
                        f"{decision.next_environment.value}; {decision.reason}"
                    ),
                    escalation_reason=(
                        "Desktop recovery strategy restricts environment fallback "
                        "to desktop-only environments"
                    ),
                )

        # Reject tool switches to non-desktop tools
        if decision.action == RecoveryAction.SWITCH_TOOL and decision.next_tool:
            non_desktop_prefixes = ("browser__", "shell__", "cloud_api__")
            if decision.next_tool.startswith(non_desktop_prefixes):
                logger.warning(
                    f"RecoveryEngine.execute: DESKTOP strategy overrides "
                    f"SWITCH_TOOL to {decision.next_tool}; escalating instead."
                )
                return RecoveryDecision(
                    task_id=decision.task_id,
                    step_id=decision.step_id,
                    action=RecoveryAction.ESCALATE,
                    reason=(
                        f"DESKTOP strategy prevented switch to non-desktop tool "
                        f"{decision.next_tool}; {decision.reason}"
                    ),
                    escalation_reason=(
                        "Desktop recovery strategy restricts tool alternatives "
                        "to desktop-only tools"
                    ),
                )

        return decision


# Global singleton
recovery_engine = RecoveryEngine()
