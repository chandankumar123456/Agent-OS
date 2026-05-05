from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
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
from ..config.settings import settings
from .workflow import WorkflowEngine
from .builder import WorkflowBuilder
from .executor import StepExecutor
from .pipeline import PipelineExecutor
from .context import TaskContext
from .router import AgentRouter
from .task_runner import TaskRunner
from ..orchestrator.event_bus import event_bus, Event


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
        self.task_runner = TaskRunner()
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

    async def _validate_input(self, query: str, config: Dict[str, Any], mode: str = "task") -> None:
        """Validate task input through guardrails. Raises UnrecoverableError on rejection."""
        try:
            from ..guardrails.validator import InputValidator
            InputValidator.validate_request(query, config, mode)
        except UnrecoverableError:
            raise
        except Exception as e:
            raise UnrecoverableError(
                f"Guardrails validation error: {e}",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.GUARDRAIL_VIOLATION,
                context={"raw_error": str(e)},
                http_status=422
            ) from e

    async def _validate_output(self, output: Dict[str, Any]) -> None:
        """Validate agent output through guardrails. Raises UnrecoverableError on rejection."""
        try:
            is_valid = await guardrails.verify_output(output)
            if not is_valid:
                logger.warning("Output validation rejected", output_keys=list(output.keys()))
                raise UnrecoverableError(
                    "Output validation rejected by guardrails",
                    error_type=ErrorType.VALIDATION_ERROR,
                    code=ErrorCode.GUARDRAIL_VIOLATION,
                    context={"output_keys": list(output.keys())},
                    http_status=422
                )
        except UnrecoverableError:
            raise
        except Exception as e:
            logger.warning(f"Output guardrails error: {e}")
            raise UnrecoverableError(
                f"Output guardrails internal error: {e}",
                error_type=ErrorType.VALIDATION_ERROR,
                code=ErrorCode.INTERNAL_ERROR,
                context={"raw_error": str(e)},
                http_status=500
            ) from e

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

    async def _execute_with_langgraph(
        self,
        query: str,
        config: Dict[str, Any],
        task_id: UUID,
        user_id: str,
        mode: str,
        resume_state: Optional[Dict[str, Any]] = None,
        resume_value: Optional[Dict[str, Any]] = None,
    ) -> AgentOutput:
        """Delegate LangGraph execution to TaskRunner."""
        return await self.task_runner.run(query, config, task_id, user_id, mode, resume_state=resume_state, resume_value=resume_value)

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

        # ── Input Guardrails Gate ──────────────────────────────────────
        try:
            await self._validate_input(query, config, mode)
        except UnrecoverableError as guard_err:
            logger.warning(f"Task rejected by guardrails: {guard_err.message}", task_id=str(task_id))
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type=guard_err.error_type.value,
                error_message=guard_err.message,
                recoverable=False,
            )

        # Try LangGraph execution first
        try:
            return await self._execute_with_langgraph(query, config, task_id, user_id, mode)
        except Exception as langgraph_err:
            err_str = str(langgraph_err)
            logger.warning(f"LangGraph execution failed, attempting checkpoint recovery: {langgraph_err}")
            await event_bus.publish(
                f"task:{task_id}",
                Event("fallback.triggered", {"task_id": str(task_id), "reason": err_str, "fallback_mode": mode}, source="orchestrator"),
            )
            # ── Checkpoint Recovery ──────────────────────────────────────
            try:
                from ..recovery.checkpoint_service import CheckpointRecoveryService
                recovery_service = CheckpointRecoveryService()
                recovered_state = await recovery_service.resume_task(str(task_id), mode, {})
                if recovered_state:
                    logger.info(f"Checkpoint recovered for task {task_id}, re-attempting LangGraph execution")
                    return await self._execute_with_langgraph(query, config, task_id, user_id, mode, resume_state=recovered_state)
            except Exception as recovery_err:
                logger.warning(f"Checkpoint recovery failed for task {task_id}: {recovery_err}")

        # falling back to legacy mode strategies
        try:
            from .modes import ModeStrategyFactory
            strategy = ModeStrategyFactory.get(mode)
            return await strategy.execute(self.runtime, self, query, config, task_id, user_id)
        except ValueError as mode_err:
            logger.error(f"Unknown mode '{mode}': {mode_err}")
            await event_bus.publish(
                f"task:{task_id}",
                Event("task.failed", {"task_id": str(task_id), "error": f"Unknown mode: {mode}"}, source="orchestrator"),
            )
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
