"""CoordinatorAgent — DEPRECATED compatibility wrapper.

All multi-agent workflow orchestration has been consolidated into
``orchestrator.agent_loop.AgentLoop``.  This module retains the Pydantic
models that tests and legacy code import from here.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .base import AgentInput, AgentOutput, AgentRole, AgentStatus


# ── Pydantic Models (retained for backward compatibility) ────────────────────

class WorkflowStep(BaseModel):
    """A single step in a multi-agent workflow."""
    step_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_role: AgentRole
    task_description: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    timeout_seconds: int = 120
    retry_count: int = 2
    required: bool = True


class WorkflowDefinition(BaseModel):
    """Defines a multi-agent workflow as a DAG of steps."""
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    user_id: str = ""
    steps: List[WorkflowStep]
    max_concurrent: int = 5
    default_timeout: int = 300

    def validate_dag(self) -> List[str]:
        """Validate that steps form a valid DAG (no cycles, no missing deps)."""
        errors: List[str] = []
        step_ids: set[str] = {s.step_id for s in self.steps}
        if len(step_ids) != len(self.steps):
            errors.append("Duplicate step IDs detected")
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(f"Step '{step.step_id}' depends on unknown step '{dep}'")
                if dep == step.step_id:
                    errors.append(f"Step '{step.step_id}' depends on itself")
        for step in self.steps:
            visited: set[str] = set()
            stack = list(step.depends_on)
            while stack:
                dep = stack.pop()
                if dep == step.step_id:
                    errors.append(f"Cycle detected involving step '{step.step_id}'")
                    break
                if dep not in visited:
                    visited.add(dep)
                    dep_step = next((s for s in self.steps if s.step_id == dep), None)
                    if dep_step:
                        stack.extend(dep_step.depends_on)
        return errors


class StepResult(BaseModel):
    """Result of executing a single workflow step."""
    step_id: str
    agent_id: Optional[str] = None
    status: AgentStatus = AgentStatus.PENDING
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    retries_used: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: float = 0.0


class CoordinationResult(BaseModel):
    """Aggregated result of a multi-agent workflow execution."""
    workflow_id: str
    task_id: str
    overall_status: AgentStatus = AgentStatus.PENDING
    step_results: Dict[str, StepResult] = Field(default_factory=dict)
    handoff_log: List[Dict[str, Any]] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    error_summary: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


# ── CoordinatorAgent ─────────────────────────────────────────────────────────

class CoordinatorAgent:
    """Thin compatibility wrapper around ``orchestrator.agent_loop.AgentLoop``.

    The real execution logic lives in ``orchestrator/agent_loop.py``.
    This class delegates to the global ``Orchestrator`` singleton so
    that legacy code paths (e.g. ``AgentRuntime`` resolving a
    ``"coordinator"`` role) continue to work.
    """

    name: str = "coordinator"
    role: AgentRole = AgentRole.PLANNER

    def __init__(self, max_concurrent: int = 5):
        self._max_concurrent = max_concurrent

    async def coordinate(
        self,
        workflow: WorkflowDefinition,
        agent_pool: Optional[Dict[AgentRole, List[str]]] = None,
    ) -> CoordinationResult:
        """Legacy API — delegates to AgentLoop.

        The ``WorkflowDefinition`` is translated into a query string and
        passed through the single ``AgentLoop`` entry point.
        """
        from ..orchestrator.core import orchestrator

        query = "; ".join(s.task_description for s in workflow.steps)
        result = await orchestrator.agent_loop.run(
            query=query,
            config={"mode": "workflow", "max_concurrent": self._max_concurrent},
            task_id=UUID(workflow.task_id) if workflow.task_id else uuid4(),
            user_id=workflow.user_id or "system",
        )

        # Map AgentOutput back to CoordinationResult for backward compat
        step_results: Dict[str, StepResult] = {}
        if isinstance(result.output_data, dict) and "steps" in result.output_data:
            for s in result.output_data["steps"]:
                sid = s.get("step_id", str(uuid4()))
                step_results[sid] = StepResult(
                    step_id=sid,
                    status=AgentStatus.SUCCESS if s.get("status") == "completed" else AgentStatus.FAILURE,
                    output_data=s.get("output_data", {}),
                )

        return CoordinationResult(
            workflow_id=workflow.workflow_id,
            task_id=workflow.task_id,
            overall_status=result.status,
            step_results=step_results,
            error_summary=result.error_message,
        )

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Delegate execution to the single ``AgentLoop`` entry point."""
        from ..orchestrator.core import orchestrator

        workflow_dict = input_data.input_data.get("workflow", {})
        query = input_data.input_data.get("query", "")
        config = input_data.input_data.get("config", {})

        if workflow_dict and not query:
            steps = workflow_dict.get("steps", [])
            query = "; ".join(s.get("task_description", "") for s in steps)
            config["mode"] = "workflow"

        if not query:
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="coordination_error",
                error_message="No query or workflow definition provided",
                recoverable=False,
            )

        return await orchestrator.agent_loop.run(
            query=query,
            config=config,
            task_id=input_data.task_id,
            user_id=input_data.input_data.get("user_id", "system"),
        )
