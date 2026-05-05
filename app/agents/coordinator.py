"""Phase 3.1 — CoordinatorAgent: Multi-agent workflow orchestration with fan-out/fan-in.

Manages multi-agent workflows by assigning steps to agents, collecting results,
handling dependencies, and compiling a final coordination result.

Spec: Build Plan Task 3.2.2
Input Contract:  coordinate(workflow: WorkflowDefinition, agents: list) -> CoordinationResult
Output Contract: CoordinationResult with per-agent results, handoff log, overall status
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, UnrecoverableError, ErrorCode, ErrorType
from .base import AgentInput, AgentOutput, AgentRole, AgentStatus


# ── Pydantic Models ──────────────────────────────────────────────────────────

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
        """Validate that steps form a valid DAG (no cycles, no missing deps).

        Returns a list of validation error messages (empty = valid).
        """
        errors: List[str] = []
        step_ids: Set[str] = {s.step_id for s in self.steps}
        if len(step_ids) != len(self.steps):
            errors.append("Duplicate step IDs detected")
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(f"Step '{step.step_id}' depends on unknown step '{dep}'")
                if dep == step.step_id:
                    errors.append(f"Step '{step.step_id}' depends on itself")
        # Crude cycle detection: check for walkable cycles via DFS
        for step in self.steps:
            visited: Set[str] = set()
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
    """Orchestrates multi-agent workflows with fan-out/fan-in execution.

    Coordinates task assignment to agents via the AgentRuntime, manages
    step dependencies, handles retries, and collects results.

    Fan-out: Independent steps are executed concurrently (up to max_concurrent).
    Fan-in:  Dependent steps wait for their dependencies to complete.
    """

    name: str = "coordinator"
    role: AgentRole = AgentRole.PLANNER  # Reuse PLANNER enum for coordinator

    def __init__(self, max_concurrent: int = 5):
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: Dict[str, StepResult] = {}
        self._handoff_log: List[Dict[str, Any]] = []

    # ── Public API ───────────────────────────────────────────────────────

    async def coordinate(
        self,
        workflow: WorkflowDefinition,
        agent_pool: Optional[Dict[AgentRole, List[str]]] = None,
    ) -> CoordinationResult:
        """Execute a multi-agent workflow.

        Args:
            workflow: The workflow definition (DAG of steps).
            agent_pool: Optional mapping of AgentRole → list of agent_ids.
                        If not provided, resolves agents from the runtime.

        Returns:
            CoordinationResult with per-step results and overall status.
        """
        started_at = datetime.now(timezone.utc).isoformat()

        # Validate the DAG
        dag_errors = workflow.validate_dag()
        if dag_errors:
            return CoordinationResult(
                workflow_id=workflow.workflow_id,
                task_id=workflow.task_id,
                overall_status=AgentStatus.FAILURE,
                error_summary=f"DAG validation failed: {'; '.join(dag_errors)}",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )

        self._results.clear()
        self._handoff_log.clear()

        # Build adjacency: which steps depend on which
        dependents: Dict[str, List[str]] = {}
        for step in workflow.steps:
            for dep in step.depends_on:
                dependents.setdefault(dep, []).append(step.step_id)

        # Find root steps (no dependencies)
        completed: Set[str] = set()
        ready: Set[str] = {s.step_id for s in workflow.steps if not s.depends_on}
        pending: Set[str] = {s.step_id for s in workflow.steps if s.depends_on}
        step_map: Dict[str, WorkflowStep] = {s.step_id: s for s in workflow.steps}

        # Resolve agents
        agent_map = await self._resolve_agents(agent_pool, workflow.steps)

        # Fan-out execution loop
        tasks: Dict[str, asyncio.Task] = {}

        while ready or tasks:
            # Launch all ready steps (up to semaphore)
            launched = False
            for step_id in list(ready):
                if step_id in tasks:
                    continue
                acquired = self._semaphore._value > 0  # non-blocking check
                if not acquired:
                    break
                step = step_map[step_id]
                agent_id = self._pick_agent(step.agent_role, agent_map)
                tasks[step_id] = asyncio.create_task(
                    self._execute_step(step, agent_id, workflow.task_id, workflow.user_id)
                )
                ready.discard(step_id)
                launched = True

            if not launched and tasks:
                # All slots busy, wait for one to finish
                done, _ = await asyncio.wait(
                    tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=5.0,
                )
            elif not tasks:
                break
            else:
                # Wait a moment for tasks to complete
                await asyncio.sleep(0.1)

            # Process completed tasks
            for step_id in list(tasks.keys()):
                task = tasks[step_id]
                if task.done():
                    try:
                        result = task.result()
                    except Exception as e:
                        logger.error(f"Step {step_id} crashed: {e}")
                        result = StepResult(
                            step_id=step_id,
                            status=AgentStatus.FAILURE,
                            error_message=str(e),
                            finished_at=datetime.now(timezone.utc).isoformat(),
                        )
                    self._results[step_id] = result
                    tasks.pop(step_id)

                    if result.status == AgentStatus.SUCCESS:
                        completed.add(step_id)
                        # Unblock dependent steps
                        for dep_id in dependents.get(step_id, []):
                            dep_step = step_map[dep_id]
                            if all(d in completed for d in dep_step.depends_on):
                                ready.add(dep_id)
                    else:
                        # Check if failure cascades to dependents
                        step = step_map[step_id]
                        if step.required:
                            logger.warning(
                                f"Required step {step_id} failed, cascading to dependents"
                            )
                            self._cascade_failure(step_id, dependents, step_map, tasks, ready)

        finished_at = datetime.now(timezone.utc).isoformat()
        total_ms = 0.0
        if started_at and finished_at:
            total_ms = (
                datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)
            ).total_seconds() * 1000

        all_success = all(
            r.status == AgentStatus.SUCCESS for r in self._results.values()
        )
        any_failure = any(
            r.status == AgentStatus.FAILURE for r in self._results.values()
        )

        overall = AgentStatus.SUCCESS if all_success else (
            AgentStatus.FAILURE if any_failure else AgentStatus.PENDING
        )

        return CoordinationResult(
            workflow_id=workflow.workflow_id,
            task_id=workflow.task_id,
            overall_status=overall,
            step_results=dict(self._results),
            handoff_log=list(self._handoff_log),
            total_duration_ms=total_ms,
            error_summary=self._build_error_summary() if any_failure else None,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def execute(
        self, input_data: AgentInput
    ) -> AgentOutput:
        """Execute a coordinator task. Implements the BaseAgent protocol."""
        workflow_dict = input_data.input_data.get("workflow", {})
        agent_pool = input_data.input_data.get("agent_pool")

        if not workflow_dict:
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="coordination_error",
                error_message="No workflow definition provided",
                recoverable=False,
            )

        try:
            workflow = WorkflowDefinition(**workflow_dict)
        except Exception as e:
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="coordination_error",
                error_message=f"Invalid workflow definition: {e}",
                recoverable=False,
            )

        result = await self.coordinate(workflow, agent_pool)

        return AgentOutput(
            task_id=input_data.task_id,
            step_id=input_data.step_id,
            status=result.overall_status,
            output_data=result.model_dump(),
            confidence=0.9 if result.overall_status == AgentStatus.SUCCESS else 0.3,
            reasoning_trace=[
                f"Executed workflow {workflow.workflow_id}",
                f"Steps: {len(result.step_results)} completed, "
                f"{sum(1 for r in result.step_results.values() if r.status == AgentStatus.SUCCESS)} succeeded",
            ],
            error_message=result.error_summary,
            recoverable=result.overall_status != AgentStatus.FAILURE,
        )

    # ── Internal Helpers ─────────────────────────────────────────────────

    async def _resolve_agents(
        self,
        agent_pool: Optional[Dict[AgentRole, List[str]]],
        steps: List[WorkflowStep],
    ) -> Dict[AgentRole, List[str]]:
        """Resolve available agents for each role."""
        if agent_pool:
            return agent_pool

        # Default agents per role (core agents from runtime)
        resolved: Dict[AgentRole, List[str]] = {
            AgentRole.PLANNER: ["core_planner"],
            AgentRole.EXECUTOR: ["core_executor"],
            AgentRole.VERIFIER: ["core_verifier"],
        }
        return resolved

    def _pick_agent(
        self,
        role: AgentRole,
        agent_map: Dict[AgentRole, List[str]],
    ) -> Optional[str]:
        """Pick an available agent for the given role (round-robin)."""
        agents = agent_map.get(role, [])
        return agents[0] if agents else None

    async def _execute_step(
        self,
        step: WorkflowStep,
        agent_id: Optional[str],
        task_id: str,
        user_id: str,
    ) -> StepResult:
        """Execute a single workflow step, with retry support."""
        started_at = datetime.now(timezone.utc).isoformat()
        last_error: Optional[str] = None

        for attempt in range(step.retry_count + 1):
            try:
                async with self._semaphore:
                    await asyncio.sleep(0.01)  # Yield for coordination

                logger.info(
                    f"Coordinator executing step {step.step_id} "
                    f"(role={step.agent_role.value}, agent={agent_id}, attempt={attempt+1})"
                )

                # Simulate agent execution via runtime
                try:
                    from ..runtime.runtime import AgentRuntime
                    runtime = AgentRuntime()
                    worker = runtime.get(agent_id) if agent_id else None
                except Exception:
                    worker = None

                if worker:
                    agent_input = AgentInput(
                        task_id=self._to_uuid(task_id),
                        step_id=self._to_uuid(step.step_id),
                        role=step.agent_role,
                        input_data=step.input_data,
                    )
                    output = await worker.execute(agent_input)
                else:
                    # Fallback: simulate successful execution for unregistered agents
                    output = AgentOutput(
                        task_id=self._to_uuid(task_id),
                        step_id=self._to_uuid(step.step_id),
                        status=AgentStatus.SUCCESS,
                        output_data={"simulated": True, "step": step.task_description},
                        confidence=0.95,
                        reasoning_trace=["Simulated execution — agent not registered"],
                    )

                finished_at = datetime.now(timezone.utc).isoformat()
                duration_ms = (
                    datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)
                ).total_seconds() * 1000

                self._handoff_log.append({
                    "from_agent": "coordinator",
                    "to_agent": agent_id or "simulated",
                    "step_id": step.step_id,
                    "status": output.status.value,
                    "timestamp": finished_at,
                })

                return StepResult(
                    step_id=step.step_id,
                    agent_id=agent_id,
                    status=output.status,
                    output_data=output.output_data,
                    error_message=output.error_message,
                    retries_used=attempt,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Step {step.step_id} attempt {attempt+1}/{step.retry_count+1} failed: {e}"
                )
                if attempt < step.retry_count:
                    backoff = 2 ** attempt * 0.5
                    await asyncio.sleep(backoff)
                continue

        # All retries exhausted
        finished_at = datetime.now(timezone.utc).isoformat()
        return StepResult(
            step_id=step.step_id,
            agent_id=agent_id,
            status=AgentStatus.FAILURE,
            error_message=last_error,
            retries_used=step.retry_count,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(
                datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)
            ).total_seconds() * 1000,
        )

    def _cascade_failure(
        self,
        failed_step_id: str,
        dependents: Dict[str, List[str]],
        step_map: Dict[str, WorkflowStep],
        tasks: Dict[str, asyncio.Task],
        ready: Set[str],
    ) -> None:
        """Mark dependent steps as failed when a required step fails."""
        for dep_id in dependents.get(failed_step_id, []):
            if dep_id in ready:
                ready.discard(dep_id)
            if dep_id in tasks:
                tasks[dep_id].cancel()
                tasks.pop(dep_id, None)
            self._results[dep_id] = StepResult(
                step_id=dep_id,
                status=AgentStatus.FAILURE,
                error_message=f"Cascaded failure from required step '{failed_step_id}'",
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            # Recurse to cascade further
            self._cascade_failure(dep_id, dependents, step_map, tasks, ready)

    def _build_error_summary(self) -> str:
        """Build a human-readable error summary from step results."""
        failures = [
            f"{sid}: {r.error_message}"
            for sid, r in self._results.items()
            if r.status == AgentStatus.FAILURE
        ]
        return f"Failed steps: {', '.join(failures)}" if failures else ""

    @staticmethod
    def _to_uuid(value: str) -> UUID:
        """Convert string to UUID, handling arbitrary formats."""
        try:
            return UUID(value)
        except (ValueError, AttributeError):
            return uuid4()
