"""TaskRunner — encapsulates LangGraph-based task execution.

This module extracts the LangGraph execution path from the Orchestrator
to enforce a clean boundary between orchestration (mode selection, delegation)
and execution (graph compilation, state management, checkpoint recovery).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from datetime import datetime

from ..agents.base import AgentOutput, AgentStatus
from ..logs.logger import logger
from ..tools.registry import tool_registry
from ..langgraph.graphs import (
    compile_task_graph,
    compile_autonomous_graph,
    compile_workflow_graph,
    compile_collaboration_graph,
    get_checkpointer,
    get_cached_graph,
)
from ..langgraph.state import AgentState

try:
    from langgraph.types import Command
except ImportError:
    Command = None
from ..orchestrator.event_bus import event_bus, Event
from ..capabilities import (
    capability_router,
    feasibility_engine,
    execution_environment,
    recovery_engine,
)
from ..capabilities.models import ExecutionEnvironment, FeasibilityResult
from ..memory.long_term import workflow_repo
from ..config import settings
from .adaptive_routing import (
    TaskComplexityRouter,
    DirectExecutor,
    LightweightSequentialExecutor,
    ExecutionTier,
    summarize_intents,
)
from ..action_v1.runner import ActionV1Runner
from ..action_v1.models import ActionStatus


class TaskRunner:
    """Compiles and invokes LangGraph state graphs for task execution."""

    def __init__(self):
        self.task_complexity_router = TaskComplexityRouter()
        self.direct_executor = DirectExecutor()
        self.sequential_executor = LightweightSequentialExecutor()
        self.action_v1 = ActionV1Runner()

    @staticmethod
    def _new_trace_id() -> str:
        return str(uuid4())

    @classmethod
    def _build_initial_state(
        cls,
        query: str,
        config: Dict[str, Any],
        task_id: UUID,
        user_id: str,
        capability_assessment: Optional[Dict[str, Any]] = None,
        feasibility_report: Optional[Dict[str, Any]] = None,
        environment_config: Optional[Dict[str, Any]] = None,
        resume_state: Optional[Dict[str, Any]] = None,
    ) -> AgentState:
        trace_id = cls._new_trace_id()
        state = AgentState(
            task_id=str(task_id),
            user_id=user_id,
            trace_id=trace_id,
            query=query,
            config=config,
            messages=[],
            plan=[],
            current_step_index=0,
            steps=[],
            step_results={},
            tool_calls=[],
            verified=False,
            verification_notes=None,
            approved=None,
            approval_reason=None,
            result={},
            error=None,
            capability_assessment=capability_assessment,
            feasibility_report=feasibility_report,
            environment_config=environment_config,
            verification_reports=[],
            recovery_decisions=[],
            created_at=datetime.utcnow().isoformat(),
            mode=config.get("mode", "task"),
            status="pending",
            max_tool_rounds=config.get("max_tool_rounds", 5),
        )
        if resume_state:
            state.update(resume_state)
        return state

    async def run(
        self,
        query: str,
        config: Dict[str, Any],
        task_id: UUID,
        user_id: str,
        mode: str,
        resume_state: Optional[Dict[str, Any]] = None,
        resume_value: Optional[Dict[str, Any]] = None,
    ) -> AgentOutput:
        """Execute a task using LangGraph compiled state graphs with capability awareness.

        Args:
            resume_value: When provided, resumes a graph paused on an interrupt
                          (e.g., human approval) by passing Command(resume=resume_value).
        """
        try:
            # ── Action V1 Fast Path ─────────────────────────────────────
            if (
                mode == "task"
                and resume_state is None
                and resume_value is None
            ):
                try:
                    action_v1_result = await self.action_v1.run(str(task_id), query, config)
                    if action_v1_result.status == ActionStatus.SUCCESS:
                        logger.info(f"[ActionV1] Fast-path success for task={task_id}")
                        await event_bus.publish(
                            f"task:{task_id}",
                            Event(
                                "action_v1.executed",
                                {"task_id": str(task_id), "capability": action_v1_result.steps_executed[0].get("tool", "unknown") if action_v1_result.steps_executed else "unknown"},
                                source="orchestrator",
                            ),
                        )
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.SUCCESS,
                            output_data=action_v1_result.output,
                        )
                    if action_v1_result.status == ActionStatus.NEEDS_HUMAN:
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.FAILURE,
                            error_type="human_fallback",
                            error_message=action_v1_result.error or "Human intervention required",
                            output_data=action_v1_result.output,
                        )
                    # For capabilities Action V1 handles, don't fall through to LangGraph
                    from ..action_v1.models import Capability
                    capability = self.action_v1.selector.classify(query)
                    if capability in (
                        Capability.BROWSER,
                        Capability.DESKTOP,
                        Capability.FILESYSTEM,
                        Capability.MULTI_STEP,
                    ):
                        logger.info(
                            f"[ActionV1] Fast-path failed for handled capability {capability.value}, "
                            f"returning failure directly to avoid LangGraph fallback"
                        )
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.FAILURE,
                            error_type="action_v1_failed",
                            error_message=action_v1_result.error or f"Action V1 failed for {capability.value}",
                            output_data=action_v1_result.output,
                        )
                    logger.info(
                        f"[ActionV1] Fast-path did not succeed ({action_v1_result.status.value}), "
                        f"falling back to LangGraph"
                    )
                except Exception as av1_err:
                    from ..action_v1.models import Capability
                    capability = self.action_v1.selector.classify(query)
                    if capability in (
                        Capability.BROWSER,
                        Capability.DESKTOP,
                        Capability.FILESYSTEM,
                        Capability.MULTI_STEP,
                    ):
                        logger.warning(
                            f"[ActionV1] Fast-path exception for handled capability {capability.value}: {av1_err}. "
                            f"Returning failure directly."
                        )
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.FAILURE,
                            error_type="action_v1_exception",
                            error_message=str(av1_err),
                        )
                    logger.warning(f"[ActionV1] Fast-path failed: {av1_err}. Falling back to LangGraph.")

            # ── Adaptive Execution Router (Tier 0 / 1 / 2) ──────────────
            should_route = (
                mode == "task"
                and resume_state is None
                and resume_value is None
            )
            if should_route:
                decision = self.task_complexity_router.classify(query)
                logger.info(
                    f"[AdaptiveRouter] task={task_id} tier={int(decision.tier)} "
                    f"reason='{decision.reason}' intents=[{summarize_intents(decision.intents)}]"
                )
                await event_bus.publish(
                    f"task:{task_id}",
                    Event(
                        "adaptive.routing.selected",
                        {
                            "tier": int(decision.tier),
                            "reason": decision.reason,
                            "intents": [intent.kind for intent in decision.intents],
                            "intent_details": [
                                {"kind": intent.kind, "argument": intent.argument}
                                for intent in decision.intents
                            ],
                            "has_multi_step": decision.has_multi_step,
                            "reasoning_depth": decision.reasoning_depth,
                            "external_dependencies": decision.uses_external_dependencies,
                        },
                        source="orchestrator",
                    ),
                )

                if decision.tier == ExecutionTier.DIRECT and decision.intents:
                    tier0_report = await self.direct_executor.execute(task_id, query, decision.intents[0])
                    if tier0_report.success:
                        await event_bus.publish(
                            f"task:{task_id}",
                            Event(
                                "adaptive.routing.executed",
                                {
                                    "tier": 0,
                                    "execution_path": tier0_report.execution_path,
                                    "actions": len(tier0_report.actions),
                                },
                                source="orchestrator",
                            ),
                        )
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.SUCCESS,
                            output_data=tier0_report.to_output(query, task_id),
                        )

                    logger.warning(
                        f"[AdaptiveRouter] task={task_id} Tier 0 failed, escalating to Tier 1: {tier0_report.error}"
                    )
                    await event_bus.publish(
                        f"task:{task_id}",
                        Event(
                            "adaptive.routing.escalated",
                            {
                                "from_tier": 0,
                                "to_tier": 1,
                                "reason": tier0_report.error or "tier_0_failed",
                            },
                            source="orchestrator",
                        ),
                    )
                    tier1_report = await self.sequential_executor.execute(task_id, query, decision.intents)
                    if tier1_report.success:
                        await event_bus.publish(
                            f"task:{task_id}",
                            Event(
                                "adaptive.routing.executed",
                                {
                                    "tier": 1,
                                    "execution_path": tier1_report.execution_path,
                                    "actions": len(tier1_report.actions),
                                    "escalated_from": 0,
                                },
                                source="orchestrator",
                            ),
                        )
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.SUCCESS,
                            output_data=tier1_report.to_output(query, task_id),
                        )

                    logger.warning(
                        f"[AdaptiveRouter] task={task_id} Tier 1 failed after escalation, escalating to Tier 2: {tier1_report.error}"
                    )
                    await event_bus.publish(
                        f"task:{task_id}",
                        Event(
                            "adaptive.routing.escalated",
                            {
                                "from_tier": 1,
                                "to_tier": 2,
                                "reason": tier1_report.error or "tier_1_failed",
                            },
                            source="orchestrator",
                        ),
                    )

                elif decision.tier == ExecutionTier.SEQUENTIAL and decision.intents:
                    tier1_report = await self.sequential_executor.execute(task_id, query, decision.intents)
                    if tier1_report.success:
                        await event_bus.publish(
                            f"task:{task_id}",
                            Event(
                                "adaptive.routing.executed",
                                {
                                    "tier": 1,
                                    "execution_path": tier1_report.execution_path,
                                    "actions": len(tier1_report.actions),
                                },
                                source="orchestrator",
                            ),
                        )
                        return AgentOutput(
                            task_id=str(task_id),
                            step_id=uuid4(),
                            status=AgentStatus.SUCCESS,
                            output_data=tier1_report.to_output(query, task_id),
                        )

                    logger.warning(
                        f"[AdaptiveRouter] task={task_id} Tier 1 failed, escalating to Tier 2: {tier1_report.error}"
                    )
                    await event_bus.publish(
                        f"task:{task_id}",
                        Event(
                            "adaptive.routing.escalated",
                            {
                                "from_tier": 1,
                                "to_tier": 2,
                                "reason": tier1_report.error or "tier_1_failed",
                            },
                            source="orchestrator",
                        ),
                    )

                await event_bus.publish(
                    f"task:{task_id}",
                    Event(
                        "adaptive.routing.executed",
                        {
                            "tier": 2,
                            "execution_path": "tier_2_full_runtime",
                            "reason": "langgraph_runtime",
                        },
                        source="orchestrator",
                    ),
                )

            # ── Capability Classification ────────────────────────────────
            assessment = capability_router.classify(query, str(task_id))
            logger.info(
                f"[Capability] task={task_id} primary={assessment.primary_capability.value} "
                f"complexity={assessment.estimated_complexity}"
            )
            await event_bus.publish(
                f"task:{task_id}",
                Event("capability.selected", {
                    "primary_capability": assessment.primary_capability.value,
                    "complexity": assessment.estimated_complexity,
                    "safety_flags": assessment.safety_flags,
                }, source="orchestrator"),
            )

            # Auto-select mode if not explicitly set
            if mode == "task" and assessment.estimated_complexity > 5:
                mode = capability_router.route(assessment)
                logger.info(f"[Capability] Auto-selected mode={mode} for task={task_id}")

            # ── Feasibility Analysis ─────────────────────────────────────
            feasibility = await feasibility_engine.check(assessment, config)
            if feasibility.result == FeasibilityResult.BLOCKED:
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.failed", {"reason": "safety_blocked", "notes": feasibility.notes}, source="orchestrator"),
                )
                return AgentOutput(
                    task_id=str(task_id),
                    step_id=uuid4(),
                    status=AgentStatus.FAILURE,
                    error_type="safety_blocked",
                    error_message="Task blocked by safety policy: " + "; ".join(feasibility.notes),
                    output_data={"feasibility": feasibility.model_dump()},
                )
            if feasibility.result == FeasibilityResult.UNSUPPORTED:
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.failed", {"reason": "unsupported", "notes": feasibility.notes}, source="orchestrator"),
                )
                return AgentOutput(
                    task_id=str(task_id),
                    step_id=uuid4(),
                    status=AgentStatus.FAILURE,
                    error_type="unsupported",
                    error_message="Task requires capabilities not available: " + "; ".join(feasibility.notes),
                    output_data={"feasibility": feasibility.model_dump()},
                )

            # ── Environment Selection ────────────────────────────────────
            env_config = feasibility_engine.select_environment(assessment, feasibility)
            execution_environment.configure(str(task_id), env_config)
            logger.info(f"[Environment] task={task_id} env={env_config.environment.value}")
            await event_bus.publish(
                f"task:{task_id}",
                Event("environment.selected", {
                    "environment": env_config.environment.value,
                    "working_dir": env_config.working_dir,
                }, source="orchestrator"),
            )

            checkpointer = get_checkpointer()
            state = self._build_initial_state(
                query, config, task_id, user_id,
                capability_assessment=assessment.model_dump(),
                feasibility_report=feasibility.model_dump(),
                environment_config=env_config.model_dump(),
                resume_state=resume_state,
            )

            if mode == "workflow":
                workflow_def = None
                workflow = await workflow_repo.get_by_task(str(task_id))
                if workflow and workflow.definition:
                    workflow_def = workflow.definition
                graph = get_cached_graph("workflow", checkpointer=checkpointer, workflow_definition=workflow_def)
            else:
                graph = get_cached_graph(mode, checkpointer=checkpointer)

            thread_config = {
                "configurable": {
                    "thread_id": str(task_id),
                    "checkpoint_ns": mode,
                }
            }

            # Enforce workflow-level timeout (slightly shorter than Celery task timeout)
            workflow_timeout = config.get("timeout", settings.TIMEOUT_DEFAULT) - 10
            if workflow_timeout < 10:
                workflow_timeout = config.get("timeout", settings.TIMEOUT_DEFAULT)

            try:
                if resume_value and Command is not None:
                    logger.info(f"[LangGraph] Resuming {mode} graph for task {task_id} with resume_value")
                    final_state = await asyncio.wait_for(
                        graph.ainvoke(Command(resume=resume_value), config=thread_config),
                        timeout=workflow_timeout,
                    )
                else:
                    logger.info(f"[LangGraph] Starting {mode} graph for task {task_id}")
                    final_state = await asyncio.wait_for(
                        graph.ainvoke(state, config=thread_config),
                        timeout=workflow_timeout,
                    )
            finally:
                # Cleanup environment regardless of success/failure
                execution_environment.cleanup(str(task_id))

            result = final_state.get("result", {})
            error = final_state.get("error")
            verified = final_state.get("verified", False)
            status = final_state.get("status", "completed")

            if error or status == "rejected":
                return AgentOutput(
                    task_id=str(task_id),
                    step_id=uuid4(),
                    status=AgentStatus.FAILURE,
                    error_type="execution_error",
                    error_message=error or "Task was rejected",
                    output_data=result,
                )

            if not verified:
                # ── Desktop Recovery Path ──────────────────────────
                env = env_config.environment
                if env == ExecutionEnvironment.DESKTOP and recovery_engine:
                    logger.info(
                        f"Desktop task verification failed; entering recovery flow for task={task_id}"
                    )
                    recovery_decision = await recovery_engine.decide(
                        task_id=str(task_id),
                        step_id=None,
                        error="Desktop verification failed",
                        current_environment=env,
                    )
                    if recovery_decision.action in (
                        "retry", "RETRY",
                    ):
                        logger.info(
                            f"Recovery decided RETRY for task={task_id}; re-running"
                        )
                        return await self.run(
                            query=query,
                            config=config,
                            task_id=task_id,
                            user_id=user_id,
                            mode=mode,
                            resume_state=resume_state,
                            resume_value=resume_value,
                        )

                return AgentOutput(
                    task_id=str(task_id),
                    step_id=uuid4(),
                    status=AgentStatus.FAILURE,
                    error_type="verification_failed",
                    error_message="Task execution completed but verification failed. The goal state was not reached.",
                    output_data=result,
                )

            return AgentOutput(
                task_id=str(task_id),
                step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data=result,
            )
        except Exception as e:
            logger.error(f"[LangGraph] Execution failed for task {task_id}: {type(e).__name__}: {e}")
            await event_bus.publish(
                f"task:{task_id}",
                Event("task.failed", {"task_id": str(task_id), "error": str(e), "stage": "langgraph"}, source="orchestrator"),
            )
            import traceback
            logger.error(traceback.format_exc())
            raise
