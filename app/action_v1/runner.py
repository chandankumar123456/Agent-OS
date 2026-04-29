"""Action V1 Runner.

Main entry point that orchestrates:
  Capability Selection → Deterministic Execution → Verification → Fallback
"""
from __future__ import annotations

from typing import Any, Dict

from .models import Capability, ExecutionContext, ActionResult, ActionStatus
from .selector import CapabilitySelector
from .executor import DeterministicExecutor
from .verifier import DeterministicVerifier
from .fallback import VisionFallback, HumanFallback
from ..tools.registry import tool_registry
from ..logs.logger import logger


class ActionV1Runner:
    """Runs Action V1 execution pipeline."""

    def __init__(self):
        self.selector = CapabilitySelector()
        self.executor = DeterministicExecutor()
        self.verifier = DeterministicVerifier()
        self.vision_fallback = VisionFallback()
        self.human_fallback = HumanFallback()

    async def run(self, task_id: str, query: str, config: Dict[str, Any]) -> ActionResult:
        """Execute a task using Action V1 pipeline."""
        logger.info(f"[ActionV1] Starting task={task_id} query='{query[:80]}'")

        # 1. Human safety check
        if self.human_fallback.should_intervene(query):
            return await self.human_fallback.request(
                ExecutionContext(task_id=task_id, query=query, capability=Capability.UNKNOWN),
                "Query contains potentially dangerous keywords"
            )

        # 2. Capability selection
        capability = self.selector.classify(query)
        available_tools = tool_registry.list_tools()
        relevant_tools = self.selector.get_tools_for_capability(capability, available_tools)

        ctx = ExecutionContext(
            task_id=task_id,
            query=query,
            capability=capability,
            config=config,
            tools_available=relevant_tools,
        )

        logger.info(f"[ActionV1] task={task_id} capability={capability.value} tools={len(relevant_tools)}")

        # 3. Deterministic execution
        result = await self.executor.execute(ctx)

        # 4. Deterministic verification (skip if already failed)
        if result.status == ActionStatus.SUCCESS:
            result = await self.verifier.verify(ctx, result)

        # 5. Vision fallback on failure
        if result.status in (ActionStatus.FAILURE, ActionStatus.PARTIAL):
            logger.info(f"[ActionV1] Deterministic execution failed, attempting vision fallback")
            result = await self.vision_fallback.attempt(ctx, result)

        logger.info(f"[ActionV1] task={task_id} final_status={result.status.value} verified={result.verification_passed}")
        return result
