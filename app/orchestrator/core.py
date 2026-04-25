from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime
from ..agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from ..agents.types import TaskStatus, StepStatus
from ..logs.logger import logger
from ..runtime.runtime import AgentRuntime
from ..logs.tracing import trace_manager
from ..memory.long_term import task_repo, trace_repo, workflow_repo, workflow_node_repo, workflow_edge_repo
from ..memory.short_term import short_term_memory
from ..guardrails.validator import guardrails
from ..orchestrator.retry import retry_with_backoff, RetryConfig, is_retryable
from ..orchestrator.errors import ErrorType, UnrecoverableError, RetryableError, ErrorCode
from ..tools.registry import tool_registry
from ..config.settings import settings
from .workflow import WorkflowEngine
from .builder import WorkflowBuilder
from .executor import StepExecutor
from .pipeline import PipelineExecutor
from .context import TaskContext
from .router import AgentRouter
from ..langgraph.graphs import (
    compile_task_graph,
    compile_autonomous_graph,
    compile_workflow_graph,
    compile_collaboration_graph,
    get_checkpointer,
)
from ..langgraph.state import AgentState
from ..mcp.client_manager import mcp_client_manager
from ..capabilities import (
    capability_router,
    feasibility_engine,
    execution_environment,
    recovery_engine,
)
from ..capabilities.models import FeasibilityResult


class Orchestrator:
    """Thin orchestrator that selects modes and aggregates results.

    All execution is delegated to:
    - AgentRuntime (agent lifecycle and execution)
    - ModeStrategyFactory (mode selection)
    - PipelineExecutor (task/workflow pipeline)
    - WorkflowBuilder (DAG construction)
    - StepExecutor (step execution)
    """

    def __init__(self):
        self.runtime = AgentRuntime()
        self.router = AgentRouter(self.runtime)
        self.workflow_engine = WorkflowEngine()
        self.workflow_builder = WorkflowBuilder()
        self.step_executor = StepExecutor()
        self.retry_config = RetryConfig(
            max_retries=settings.MAX_RETRIES,
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0
        )
        self.pipeline_executor = PipelineExecutor(self)

    def _get_agent(self, agent_type: str):
        """Get an agent from the Router. Runtime is the ONLY execution entry point."""
        agent = self.router.resolve(agent_type)
        if not agent:
            raise RuntimeError(
                f"Agent for role '{agent_type}' not found in runtime. "
                f"Ensure AgentRuntime.initialize() was called at startup."
            )
        return agent

    async def _load_task_state(self, context: TaskContext) -> None:
        try:
            db_task = await task_repo.get(str(context.task_id))
            if db_task and db_task.result and isinstance(db_task.result, dict):
                context.result = db_task.result
                logger.info(f"Loaded task from DB: {context.task_id}")
        except Exception as e:
            logger.warning(f"Task state load failed, using fresh context: {e}")

    async def _save_task_state(self, context: TaskContext) -> None:
        try:
            await task_repo.update(
                str(context.task_id),
                status=context.status.value,
                result=context.result,
                error=str(context.error) if context.error else None,
            )
            logger.info(f"Saved task to DB: {context.task_id}")
        except Exception as e:
            logger.error(f"DB save failed: {e}")
            raise

    async def _hydrate_memory_context(self, context: TaskContext) -> Dict[str, Any]:
        try:
            cached = await short_term_memory.get_context(str(context.task_id))
            if cached:
                context.context.update(cached)
        except Exception as e:
            logger.warning(f"Short-term memory hydration failed: {e}")

        try:
            recent_tasks = await task_repo.list_by_user(context.user_id, limit=3)
            if recent_tasks:
                context.context["recent_tasks"] = [
                    {"query": t.query, "status": t.status, "result_summary": str(t.result)[:200] if t.result else None}
                    for t in recent_tasks if t.id != str(context.task_id)
                ]
        except Exception as e:
            logger.warning(f"Recent tasks hydration failed: {e}")

        return context.context

    async def _validate_input(self, query: str, config: Dict[str, Any]) -> bool:
        try:
            validation_result = await guardrails.validator.validate({"query": query, "config": config})
            if not validation_result.valid:
                logger.warning(f"Input validation failed: {validation_result.errors}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Guardrails validation error: {e}")
            return False

    async def _validate_output(self, output: Dict[str, Any]) -> bool:
        try:
            is_valid = await guardrails.verify_output(output)
            if not is_valid:
                logger.warning("Output validation failed")
                return False
            return True
        except Exception as e:
            logger.warning(f"Output guardrails error: {e}")
            return False

    async def _execute_with_retry(self, agent, input_data: AgentInput, role: Optional[str] = None) -> AgentOutput:
        async def _execute(target_agent):
            return await target_agent.execute(input_data)
        try:
            return await retry_with_backoff(lambda: _execute(agent), self.retry_config)
        except Exception as e:
            logger.error(f"Primary agent execution failed after retries: {e}")
            # Attempt fallback agent if role is provided
            if role:
                fallback_chain = self.router.list_roles().get(role, [])
                for fallback_id in fallback_chain:
                    fallback_worker = self.runtime.get(fallback_id)
                    if fallback_worker and fallback_worker.agent_instance is not agent:
                        try:
                            logger.info(f"Trying fallback agent '{fallback_id}' for role '{role}'")
                            result = await fallback_worker.agent_instance.execute(input_data)
                            if result.status == AgentStatus.SUCCESS:
                                logger.info(f"Fallback agent '{fallback_id}' succeeded for role '{role}'")
                                return result
                        except Exception as fe:
                            logger.warning(f"Fallback agent '{fallback_id}' failed: {fe}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="execution_error",
                error_message=str(e),
                recoverable=is_retryable(e, self.retry_config)
            )

    async def _run_step(self, task_id, trace_id, context, step_row, tools_schema, config):
        return await self.step_executor.execute(
            task_id=task_id,
            trace_id=trace_id,
            context=context,
            step_row=step_row,
            tools_schema=tools_schema,
            config=config or {},
            agent_instance=self._get_agent("executor"),
        )

    async def _build_workflow(self, task_id, user_id, steps):
        return await self.workflow_builder.build(task_id, user_id, steps)

    async def _get_workflow_state(self, task_id: UUID) -> Dict[str, Any]:
        workflow = await workflow_repo.get_by_task(str(task_id))
        if not workflow:
            return {"workflow": None, "nodes": [], "edges": []}
        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        edges = await workflow_edge_repo.get_by_workflow(workflow.id)
        return {"workflow": workflow, "nodes": nodes, "edges": edges}

    def _serialize_workflow_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return self.workflow_builder.serialize_state(state)

    def _new_trace_id(self) -> str:
        return str(uuid4())

    def _create_task_context(self, task_id: UUID, user_id: str, query: str, config: Optional[Dict[str, Any]]) -> TaskContext:
        return TaskContext(task_id, user_id, query, config)

    def _is_task_complete(self, output_data: Dict[str, Any]) -> bool:
        if not output_data:
            return False
        result = output_data.get("result", "")
        if isinstance(result, str):
            return any(keyword in result.lower() for keyword in ["complete", "done", "finished", "success"])
        return output_data.get("complete", False)

    async def _save_final_state(self, context: TaskContext, combined_result: Dict[str, Any], verify_result) -> None:
        # Defensively ensure trace_id is present in the result for trace retrieval
        if context.trace_id and "trace_id" not in combined_result:
            combined_result["trace_id"] = context.trace_id
        context.result = combined_result
        context.status = TaskStatus.COMPLETED
        await self._save_task_state(context)
        await short_term_memory.save_context(str(context.task_id), context.context, expire=1800)
        await trace_repo.update_status(context.trace_id, TaskStatus.COMPLETED.value)

    def _build_initial_state(
        self,
        query: str,
        config: Dict[str, Any],
        task_id: UUID,
        user_id: str,
        capability_assessment: Optional[Dict[str, Any]] = None,
        feasibility_report: Optional[Dict[str, Any]] = None,
        environment_config: Optional[Dict[str, Any]] = None,
    ) -> AgentState:
        trace_id = self._new_trace_id()
        return AgentState(
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

    async def _execute_with_langgraph(
        self,
        query: str,
        config: Dict[str, Any],
        task_id: UUID,
        user_id: str,
        mode: str,
    ) -> AgentOutput:
        """Execute a task using LangGraph compiled state graphs with capability awareness."""
        try:
            # ── Capability Classification ────────────────────────────────
            assessment = capability_router.classify(query, str(task_id))
            logger.info(
                f"[Capability] task={task_id} primary={assessment.primary_capability.value} "
                f"complexity={assessment.estimated_complexity}"
            )

            # Auto-select mode if not explicitly set
            if mode == "task" and assessment.estimated_complexity > 5:
                mode = capability_router.route(assessment)
                logger.info(f"[Capability] Auto-selected mode={mode} for task={task_id}")

            # ── Feasibility Analysis ─────────────────────────────────────
            feasibility = await feasibility_engine.check(assessment, config)
            if feasibility.result == FeasibilityResult.BLOCKED:
                return AgentOutput(
                    task_id=str(task_id),
                    step_id=uuid4(),
                    status=AgentStatus.FAILURE,
                    error_type="safety_blocked",
                    error_message="Task blocked by safety policy: " + "; ".join(feasibility.notes),
                    output_data={"feasibility": feasibility.model_dump()},
                )
            if feasibility.result == FeasibilityResult.UNSUPPORTED:
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

            # Ensure MCP tools are discovered
            await tool_registry.discover_mcp_tools()

            checkpointer = get_checkpointer()
            state = self._build_initial_state(
                query, config, task_id, user_id,
                capability_assessment=assessment.model_dump(),
                feasibility_report=feasibility.model_dump(),
                environment_config=env_config.model_dump(),
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
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def execute_task(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        task_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
    ) -> AgentOutput:
        task_id = task_id or uuid4()
        if not user_id:
            user_id = "system"
        config = config or {}
        mode = config.get("mode", "task")

        # Try LangGraph execution first
        try:
            return await self._execute_with_langgraph(query, config, task_id, user_id, mode)
        except Exception as langgraph_err:
            logger.warning(f"LangGraph execution failed, falling back to legacy mode strategy: {langgraph_err}")

        # Fallback to legacy mode strategies
        try:
            from .modes import ModeStrategyFactory
            strategy = ModeStrategyFactory.get(mode)
            return await strategy.execute(self.runtime, self, query, config, task_id, user_id)
        except ValueError as mode_err:
            logger.error(f"Unknown mode '{mode}': {mode_err}")
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type="invalid_mode",
                error_message=f"Unknown execution mode: {mode}",
                recoverable=False,
            )

    async def _execute_pipeline(self, query, config=None, task_id=None, user_id=None):
        return await self.pipeline_executor.execute(query, config, task_id, user_id)

    async def run_workflow(self, query: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config = config or {}
        config["mode"] = "workflow"
        result = await self.execute_task(query, config)
        if result.status != AgentStatus.SUCCESS:
            raise UnrecoverableError(
                result.error_message or "Workflow execution failed",
                ErrorType.EXECUTION_ERROR,
            )
        return result.output_data


orchestrator = Orchestrator()
