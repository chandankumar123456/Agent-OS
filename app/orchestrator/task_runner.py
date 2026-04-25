"""TaskRunner — encapsulates LangGraph-based task execution.

This module extracts the LangGraph execution path from the Orchestrator
to enforce a clean boundary between orchestration (mode selection, delegation)
and execution (graph compilation, state management, checkpoint recovery).
"""
from __future__ import annotations

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
)
from ..langgraph.state import AgentState
from ..orchestrator.v2.event_bus import event_bus, Event
from ..capabilities import (
    capability_router,
    feasibility_engine,
    execution_environment,
)
from ..capabilities.models import FeasibilityResult
from ..memory.long_term import workflow_repo


class TaskRunner:
    """Compiles and invokes LangGraph state graphs for task execution."""

    def __init__(self):
        pass

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
    ) -> AgentOutput:
        """Execute a task using LangGraph compiled state graphs with capability awareness."""
        try:
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

            # Ensure MCP tools are discovered
            await tool_registry.discover_mcp_tools()

            checkpointer = get_checkpointer()
            state = self._build_initial_state(
                query, config, task_id, user_id,
                capability_assessment=assessment.model_dump(),
                feasibility_report=feasibility.model_dump(),
                environment_config=env_config.model_dump(),
                resume_state=resume_state,
            )

            if mode == "task":
                graph = compile_task_graph(checkpointer=checkpointer)
            elif mode == "autonomous":
                graph = compile_autonomous_graph(checkpointer=checkpointer)
            elif mode == "workflow":
                workflow_def = None
                workflow = await workflow_repo.get_by_task(str(task_id))
                if workflow and workflow.definition:
                    workflow_def = workflow.definition
                graph = compile_workflow_graph(workflow_definition=workflow_def, checkpointer=checkpointer)
            elif mode == "collaboration":
                graph = compile_collaboration_graph(checkpointer=checkpointer)
            else:
                graph = compile_task_graph(checkpointer=checkpointer)

            thread_config = {
                "configurable": {
                    "thread_id": str(task_id),
                    "checkpoint_ns": mode,
                }
            }

            logger.info(f"[LangGraph] Starting {mode} graph for task {task_id}")
            final_state = await graph.ainvoke(state, config=thread_config)

            # Cleanup environment
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
