"""
AgentLoop — the real, dynamic agent execution loop.

Plan → Execute DAG → Observe → Replan → Repeat

Uses WorkflowEngine for DAG execution with parallel support.
Calls PlannerAgent and ExecutorAgent dynamically via AgentRuntime.
Every decision is dynamically generated — no keyword routing, no static plans.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from ..agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from ..agents.types import TaskStatus, StepStatus
from ..logs.logger import logger
from ..logs.tracing import trace_manager
from ..memory.long_term import (
    task_repo,
    trace_repo,
    node_trace_repo,
    workflow_node_repo,
)
from ..memory.short_term import short_term_memory
from ..orchestrator.errors import (
    ErrorType,
    UnrecoverableError,
    WorkflowPausedForApproval,
    ErrorCode,
)
from ..orchestrator.retry import RetryConfig
from ..tools.registry import tool_registry
from ..guardrails.validator import guardrails

from .workflow import WorkflowEngine, WorkflowNode
from .builder import WorkflowBuilder
from .executor import StepExecutor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = 10
DEFAULT_MAX_REPLANS = 3


# ---------------------------------------------------------------------------
# AgentLoop
# ---------------------------------------------------------------------------

class AgentLoop:
    """Real agent loop with plan → execute DAG → observe → replan cycles.

    Each iteration:
        1. **Plan / Replan** — calls PlannerAgent (via AgentRuntime) to
           generate or update the execution plan. On replan, all prior
           tool outputs and observed results are fed back into the
           reasoning context so the planner can adapt dynamically.
        2. **Build DAG** — converts the plan into a validated, persisted
           workflow DAG via WorkflowBuilder.
        3. **Execute DAG** — runs the DAG through
           WorkflowEngine.execute_graph(), which executes independent
           nodes in parallel while respecting dependencies.
        4. **Observe** — collects results from every node, updates the
           accumulated reasoning context, persists state.
        5. **Check completion** — if all required steps succeeded and
           verification passes, the loop terminates. Otherwise it
           replans with the updated context.
        6. **Replan on failure** — if any required step fails, the
           failure context is fed back to the planner so it can adapt.

    This class is the **single execution entry point** for all task
    modes.  It replaces both the legacy ``_execute_pipeline`` and
    ``_execute_with_langgraph`` paths.
    """

    # ── configuration ────────────────────────────────────────────────

    DEFAULT_MAX_ITERATIONS: int = DEFAULT_MAX_ITERATIONS

    # ── constructor ──────────────────────────────────────────────────

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.runtime = orchestrator.runtime
        self.router = orchestrator.router
        self.workflow_engine = WorkflowEngine()
        self.workflow_builder = WorkflowBuilder()
        self.step_executor = StepExecutor()
        self.retry_config: RetryConfig = orchestrator.retry_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        task_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
    ) -> AgentOutput:
        """Execute a task through the full agent loop.

        Parameters
        ----------
        query : str
            The user's natural-language task description.
        config : dict, optional
            Execution configuration (mode, timeout, etc.).
        task_id : UUID, optional
            Task identifier. Generated if not provided.
        user_id : str, optional
            Owning user. Defaults to ``"system"``.

        Returns
        -------
        AgentOutput
            Final result including status, output data, and reasoning trace.
        """
        # ── Normalise inputs ─────────────────────────────────────────
        task_id = task_id or uuid4()
        user_id = user_id or "system"
        config = config or {}

        # ── Trace setup ──────────────────────────────────────────────
        trace_id = str(uuid4())

        main_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="agent_loop",
            agent_name="orchestrator",
            metadata={"query": query, "task_id": str(task_id), "mode": config.get("mode", "task")},
        )

        try:
            await trace_repo.create(
                str(task_id), trace_id, user_id,
                status=TaskStatus.RUNNING.value,
            )
        except Exception as e:
            logger.warning(f"Trace row creation failed, continuing: {e}")

        # ── Task context ─────────────────────────────────────────────
        from .context import TaskContext
        context = TaskContext(task_id, user_id, query, config)
        context.trace_id = trace_id

        # ── Hydrate from DB & memory ────────────────────────────────
        try:
            await self.orchestrator._load_task_state(context)
        except Exception as e:
            logger.warning(f"Task state load failed: {e}")

        try:
            await self.orchestrator._hydrate_memory_context(context)
        except Exception as e:
            logger.warning(f"Memory hydration failed: {e}")

        # ── Tools schema ─────────────────────────────────────────────
        tools_schema = tool_registry.list_tools()

        # ── Accumulated execution state ──────────────────────────────
        all_step_results: List[Dict[str, Any]] = []
        completed_step_ids: set = set()
        failed_step_ids: set = set()
        reasoning_context: Dict[str, Any] = dict(context.context)

        max_iterations = config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

        # ── AGENT LOOP ───────────────────────────────────────────────
        for iteration in range(1, max_iterations + 1):
            logger.info(
                f"[AgentLoop] Iteration {iteration}/{max_iterations} for task {task_id}"
            )

            # ── 1. PLAN / REPLAN ────────────────────────────────────
            plan_result, plan_steps = await self._plan(
                query=query,
                tools_schema=tools_schema,
                context=context,
                reasoning_context=reasoning_context,
                completed_steps=all_step_results,
                iteration=iteration,
                trace_id=trace_id,
            )

            if plan_result.status != AgentStatus.SUCCESS:
                return await self._build_error_output(
                    task_id, "planning_failed",
                    plan_result.error_message or "Planner failed",
                    context, trace_id, main_span,
                )

            if not plan_steps:
                logger.info(f"[AgentLoop] Planner returned empty plan at iteration {iteration} — task complete")
                break

            # Filter out already-completed steps
            remaining_steps = [
                s for s in plan_steps
                if s.get("id") not in completed_step_ids
            ]
            if not remaining_steps:
                logger.info(f"[AgentLoop] All planned steps already completed at iteration {iteration} — task complete")
                break

            # ── 2. BUILD DAG ────────────────────────────────────────
            for step in remaining_steps:
                step["user_id"] = user_id

            workflow_state = await self.workflow_builder.build(
                task_id, user_id, remaining_steps,
            )
            workflow = workflow_state["workflow"]
            persisted_nodes = workflow_state["nodes"]

            # Build mapping: planner step ID → DB node UUID
            planner_to_db: Dict[str, str] = {}
            node_lookup: Dict[str, Any] = {}
            for node in persisted_nodes:
                raw_step = (node.input_data or {}).get("raw_step", {})
                planner_id = str(raw_step.get("id", node.step_number))
                planner_to_db[planner_id] = str(node.id)
                node_lookup[str(node.id)] = node

            # Convert persisted model rows → WorkflowNode dataclasses
            workflow_nodes: List[WorkflowNode] = []
            for node in persisted_nodes:
                workflow_nodes.append(
                    WorkflowNode(
                        id=str(node.id),
                        step=str(node.input_data.get("step", "")) if node.input_data else "",
                        agent_type=str(node.agent_type or "executor"),
                        depends_on=[
                            planner_to_db.get(dep, dep)
                            for dep in (node.depends_on or [])
                        ],
                        condition=str(node.condition_code) if node.condition_code else None,
                        step_number=int(node.step_number or 0),
                        node_type=str(node.node_type or "agent"),
                        approval_config=node.approval_config,
                    )
                )

            # Update context with step metadata
            context.steps = [
                {
                    "step_id": str(node.id),
                    "task_id": str(task_id),
                    "step_number": node.step_number,
                    "agent_type": node.agent_type,
                    "depends_on": node.depends_on or [],
                    "input_data": node.input_data or {},
                    "node_type": str(node.node_type or "agent"),
                    "approval_config": node.approval_config,
                }
                for node in persisted_nodes
            ]

            # ── 3. EXECUTE DAG ──────────────────────────────────────
            step_data_map: Dict[str, Dict[str, Any]] = {
                str(node.id): {
                    "raw_step": (
                        (node.input_data or {}).get("raw_step", {})
                        if node.input_data
                        else {}
                    ),
                    "step_description": (
                        node.input_data.get("step", "") if node.input_data else ""
                    ),
                }
                for node in persisted_nodes
            }

            async def run_node(
                node: WorkflowNode,
                running_context: Dict[str, Any],
            ) -> Dict[str, Any]:
                """Closure that executes a single DAG node via the runtime."""
                node_row = node_lookup.get(node.id)
                if not node_row:
                    raise UnrecoverableError(
                        f"Workflow node {node.id} not found in persisted nodes",
                        ErrorType.SYSTEM_ERROR,
                        ErrorCode.INTERNAL_ERROR,
                    )

                # Resolve agent dynamically — NO keyword routing
                agent_instance = (
                    self.router.resolve(node.agent_type)
                    or self.orchestrator._get_agent("executor")
                )

                step_meta = step_data_map.get(node.id, {})
                raw_step = step_meta.get("raw_step", {})

                result = await self.step_executor.execute(
                    task_id=task_id,
                    trace_id=trace_id,
                    context=context,
                    step_row={
                        "step_id": node_row.id,
                        "step_number": node_row.step_number,
                        "agent_type": node_row.agent_type,
                        "input_data": node_row.input_data or {},
                        "node_type": str(node_row.node_type or "agent"),
                        "approval_config": node_row.approval_config,
                    },
                    tools_schema=tools_schema,
                    config=config,
                    agent_instance=agent_instance,
                )

                # Persist node outcome
                try:
                    await workflow_node_repo.update(
                        node_row.id,
                        status=result.get("status", StepStatus.COMPLETED.value),
                        output_data=result.get("output_data"),
                        confidence=result.get("confidence"),
                    )
                except Exception as e:
                    logger.warning(f"[AgentLoop] Node outcome persist failed: {e}")

                return result

            try:
                dag_result = await self.workflow_engine.execute_graph(
                    workflow_nodes,
                    {"run_node": run_node},
                    reasoning_context,
                )
            except WorkflowPausedForApproval as pause:
                logger.info(f"[AgentLoop] Workflow paused for approval at node {pause.node_id}")
                try:
                    await task_repo.update(
                        str(task_id),
                        status=TaskStatus.WAITING_APPROVAL.value,
                    )
                except Exception as e:
                    logger.warning(f"[AgentLoop] Approval state persist failed: {e}")
                try:
                    await trace_repo.update_status(trace_id, TaskStatus.WAITING_APPROVAL.value)
                except Exception as e:
                    logger.warning(f"[AgentLoop] Approval trace update failed: {e}")
                trace_manager.end_span(main_span, "paused", f"Waiting approval at {pause.node_id}")
                try:
                    await trace_manager.persist_trace(trace_id)
                except Exception as e:
                    logger.warning(f"[AgentLoop] Approval trace persist failed: {e}")
                return AgentOutput(
                    task_id=task_id,
                    step_id=uuid4(),
                    status=AgentStatus.PENDING,
                    output_data={
                        "query": query,
                        "status": "waiting_approval",
                        "node_id": pause.node_id,
                        "approval_config": pause.approval_config,
                        "trace_id": trace_id,
                        "mode": context.mode,
                    },
                    reasoning_trace=[f"Paused for approval at node {pause.node_id}"],
                )

            # ── 4. OBSERVE ──────────────────────────────────────────
            iteration_results: List[Dict[str, Any]] = []
            iteration_failures: List[Dict[str, Any]] = []

            for node_id, node_result in dag_result["nodes"].items():
                status = node_result["status"]
                output = node_result.get("output", {})

                if status == "skipped":
                    try:
                        await workflow_node_repo.update(
                            node_id, status=StepStatus.SKIPPED.value,
                        )
                    except Exception as e:
                        logger.warning(f"[AgentLoop] Skipped node persist failed: {e}")
                    try:
                        await node_trace_repo.create(
                            task_id=str(task_id),
                            user_id=user_id,
                            trace_id=trace_id,
                            node_id=node_id,
                            status=StepStatus.SKIPPED.value,
                            input_data=next(
                                (n.input_data for n in persisted_nodes if str(n.id) == node_id),
                                {},
                            ),
                        )
                    except Exception as e:
                        logger.warning(f"[AgentLoop] Skipped node trace persist failed: {e}")
                    continue

                step_entry = {
                    "step_id": node_id,
                    "status": status,
                    "output_data": output,
                }
                iteration_results.append(step_entry)

                if status == "completed":
                    completed_step_ids.add(node_id)
                elif status in ("failed", "failure"):
                    failed_step_ids.add(node_id)
                    iteration_failures.append(step_entry)

            all_step_results.extend(iteration_results)

            # ── Update reasoning context ────────────────────────────
            reasoning_context["_iteration"] = iteration
            reasoning_context["_completed_steps"] = [
                {"id": s["step_id"], "output": s.get("output_data")}
                for s in all_step_results
                if s["step_id"] in completed_step_ids
            ]
            reasoning_context["_failed_steps"] = [
                {"id": s["step_id"], "output": s.get("output_data")}
                for s in all_step_results
                if s["step_id"] in failed_step_ids
            ]
            # Fold node outputs into context for downstream condition evaluation
            for node_id, node_result in dag_result["nodes"].items():
                if node_result["status"] == "completed":
                    reasoning_context[node_id] = node_result.get("output", {})

            # ── 5. CHECK COMPLETION ────────────────────────────────
            if iteration_failures and iteration < max_iterations:
                logger.warning(
                    f"[AgentLoop] {len(iteration_failures)} step(s) failed at "
                    f"iteration {iteration}; replanning with failure context"
                )
                continue  # replan in next iteration

            # All steps this iteration succeeded — verify and possibly finish
            verify_result = await self._verify(
                task_id=task_id,
                trace_id=trace_id,
                context=context,
                iteration_results=iteration_results,
            )

            if verify_result.status == AgentStatus.SUCCESS:
                logger.info(
                    f"[AgentLoop] Verification passed at iteration {iteration} — task complete"
                )
                break

            logger.info(
                f"[AgentLoop] Verification not passed at iteration {iteration}; "
                f"replanning if iterations remain"
            )
            # Loop continues — planner will see updated context

        # ── POST-LOOP: Build final result ────────────────────────────
        return await self._build_success_output(
            query=query,
            task_id=task_id,
            trace_id=trace_id,
            context=context,
            all_step_results=all_step_results,
            reasoning_context=reasoning_context,
            main_span=main_span,
        )

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _plan(
        self,
        query: str,
        tools_schema: List[Dict[str, Any]],
        context: Any,  # TaskContext
        reasoning_context: Dict[str, Any],
        completed_steps: List[Dict[str, Any]],
        iteration: int,
        trace_id: str,
    ) -> Tuple[AgentOutput, List[Dict[str, Any]]]:
        """Call the PlannerAgent (via AgentRuntime) to generate or update the plan.

        On replan (iteration > 1), previously observed results are fed into
        the planner's reasoning context so it can adapt dynamically.
        """

        plan_span = trace_manager.start_span(
            trace_id=trace_id,
            operation=f"planning_iter_{iteration}",
            agent_name="planner",
            metadata={"iteration": iteration, "query": query},
        )

        # Build a context-rich query for replanning
        if iteration > 1 and completed_steps:
            planning_query = self._build_replanning_query(
                original_query=query,
                completed_steps=completed_steps,
                reasoning_context=reasoning_context,
                iteration=iteration,
            )
        else:
            planning_query = query

        plan_input = AgentInput(
            task_id=context.task_id,
            step_id=uuid4(),
            role=AgentRole.PLANNER,
            input_data={
                "query": planning_query,
                "tools": tools_schema,
                "mode": context.mode,
                "iteration": iteration,
                "previous_results": [
                    {
                        "step_id": s.get("step_id"),
                        "output": s.get("output_data"),
                        "status": s.get("status"),
                    }
                    for s in completed_steps
                ] if completed_steps else [],
            },
            context=reasoning_context,
            constraints=context.config,
        )

        planner_agent = self.router.resolve("planner")
        if not planner_agent:
            return AgentOutput(
                task_id=context.task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type="agent_not_found",
                error_message="Planner agent not registered in runtime",
                recoverable=False,
            ), []

        plan_result = await self.orchestrator._execute_with_retry(
            planner_agent, plan_input, role="planner"
        )

        trace_manager.end_span(
            plan_span,
            "success" if plan_result.status == AgentStatus.SUCCESS else "failure",
        )
        try:
            await trace_manager.persist_span(plan_span)
        except Exception as e:
            logger.warning(f"[AgentLoop] Plan span persist failed: {e}")

        if plan_result.status == AgentStatus.FAILURE:
            return plan_result, []

        steps = plan_result.output_data.get("steps", [])
        if not isinstance(steps, list):
            logger.warning(
                f"[AgentLoop] Planner returned non-list steps: {type(steps)}"
            )
            return plan_result, []

        # Validate step structure
        valid_steps: List[Dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                logger.warning(f"[AgentLoop] Skipping non-dict step: {step}")
                continue
            if not step.get("step"):
                logger.warning(f"[AgentLoop] Skipping step with no description: {step}")
                continue
            valid_steps.append(step)

        logger.info(
            f"[AgentLoop] Planner returned {len(valid_steps)} step(s) "
            f"at iteration {iteration}"
        )
        return plan_result, valid_steps

    # ------------------------------------------------------------------
    # Replanning query builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_replanning_query(
        original_query: str,
        completed_steps: List[Dict[str, Any]],
        reasoning_context: Dict[str, Any],
        iteration: int,
    ) -> str:
        """Construct a planning query that includes prior execution context.

        The planner sees what was already done, what succeeded, what failed,
        and the accumulated state, so it can generate an informed next plan.
        """
        parts: List[str] = []

        parts.append(f"Original task: {original_query}")
        parts.append(f"\nIteration: {iteration}")
        parts.append("\nSteps already completed:")

        for step in completed_steps:
            sid = step.get("step_id", "?")
            status = step.get("status", "unknown")
            output = step.get("output_data", {})
            output_summary = str(output)[:400] if output else "(no output)"
            parts.append(f"  - [{status}] {sid}: {output_summary}")

        failed_steps_data = reasoning_context.get("_failed_steps", [])
        if failed_steps_data:
            parts.append("\nSteps that FAILED and need attention:")
            for fs in failed_steps_data:
                parts.append(f"  - {fs.get('id', '?')}: {str(fs.get('output', {}))[:300]}")

        parts.append(
            "\nBased on the results above, generate a plan for the REMAINING "
            "steps needed to fully complete the original task. "
            "Do NOT repeat steps that already succeeded. "
            "Only include steps that are still needed."
        )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    async def _verify(
        self,
        task_id: UUID,
        trace_id: str,
        context: Any,
        iteration_results: List[Dict[str, Any]],
    ) -> AgentOutput:
        """Call the Verifier agent to confirm task completion."""
        verify_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="verification",
            agent_name="verifier",
            metadata={"steps": len(iteration_results)},
        )

        verify_input = AgentInput(
            task_id=task_id,
            step_id=uuid4(),
            role=AgentRole.VERIFIER,
            input_data={"output": iteration_results},
            context=context.context,
        )

        verifier_agent = self.router.resolve("verifier")
        if not verifier_agent:
            # No verifier registered — optimistically consider done
            trace_manager.end_span(verify_span, "success")
            try:
                await trace_manager.persist_span(verify_span)
            except Exception as e:
                logger.warning(f"[AgentLoop] Verify span persist failed: {e}")
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"valid": True, "note": "no verifier registered"},
            )

        verify_result = await self.orchestrator._execute_with_retry(
            verifier_agent, verify_input, role="verifier"
        )

        trace_manager.end_span(
            verify_span,
            "success" if verify_result.status == AgentStatus.SUCCESS else "failure",
        )
        try:
            await trace_manager.persist_span(verify_span)
        except Exception as e:
            logger.warning(f"[AgentLoop] Verify span persist failed: {e}")

        return verify_result

    # ------------------------------------------------------------------
    # Output builders
    # ------------------------------------------------------------------

    async def _build_success_output(
        self,
        query: str,
        task_id: UUID,
        trace_id: str,
        context: Any,
        all_step_results: List[Dict[str, Any]],
        reasoning_context: Dict[str, Any],
        main_span: Any,
    ) -> AgentOutput:
        """Assemble the final success output, persist state, and clean up traces."""
        combined_result = {
            "query": query,
            "steps": all_step_results,
            "trace_id": trace_id,
            "mode": context.mode,
            "total_iterations": reasoning_context.get("_iteration", 1),
        }

        try:
            is_valid = await guardrails.verify_output(combined_result)
            if not is_valid:
                logger.warning("[AgentLoop] Output validation rejected by guardrails")
                return await self._build_error_output(
                    task_id, "guardrail_violation",
                    "Output validation rejected by guardrails",
                    context, trace_id, main_span,
                )
        except Exception as e:
            logger.warning(f"[AgentLoop] Output guardrails error: {e}")

        context.result = combined_result
        context.status = TaskStatus.COMPLETED

        try:
            await task_repo.update(
                str(task_id),
                status=TaskStatus.COMPLETED.value,
                result=combined_result,
            )
        except Exception as e:
            logger.error(f"[AgentLoop] DB save failed: {e}")

        try:
            await short_term_memory.save_context(
                str(task_id), context.context, expire=1800,
            )
        except Exception as e:
            logger.warning(f"[AgentLoop] Short-term memory save failed: {e}")

        try:
            await trace_repo.update_status(trace_id, TaskStatus.COMPLETED.value)
        except Exception as e:
            logger.warning(f"[AgentLoop] Trace status update failed: {e}")
        trace_manager.end_span(main_span, "success")
        try:
            await trace_manager.persist_trace(trace_id)
        except Exception as e:
            logger.warning(f"[AgentLoop] Trace persist failed: {e}")

        return AgentOutput(
            task_id=task_id,
            step_id=uuid4(),
            status=AgentStatus.SUCCESS,
            output_data=combined_result,
            confidence=0.9,
            reasoning_trace=[
                f"Agent loop completed with {len(all_step_results)} total step results",
                f"Trace: {trace_id}",
                f"Mode: {context.mode}",
            ],
        )

    async def _build_error_output(
        self,
        task_id: UUID,
        error_type: str,
        error_message: str,
        context: Any,
        trace_id: str,
        main_span: Any,
    ) -> AgentOutput:
        """Assemble a failure output, persist state, and clean up traces."""
        context.error = error_message
        context.status = TaskStatus.FAILED

        try:
            await task_repo.update(
                str(task_id),
                status=TaskStatus.FAILED.value,
                error=error_message,
            )
        except Exception as e:
            logger.error(f"[AgentLoop] Error state DB save failed: {e}")

        try:
            await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
        except Exception as e:
            logger.warning(f"[AgentLoop] Trace status update failed: {e}")
        trace_manager.end_span(main_span, "failure", error_message)
        try:
            await trace_manager.persist_trace(trace_id)
        except Exception as e:
            logger.warning(f"[AgentLoop] Trace persist failed: {e}")

        return AgentOutput(
            task_id=task_id,
            step_id=uuid4(),
            status=AgentStatus.FAILURE,
            error_type=error_type,
            error_message=error_message,
            recoverable=False,
        )
