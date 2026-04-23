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
from ..tools.registry import tool_registry
from ..config.settings import settings
from .workflow import WorkflowEngine
from .builder import WorkflowBuilder
from .executor import StepExecutor
from .pipeline import PipelineExecutor
from .context import TaskContext


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
        """Get an agent from the Runtime. Runtime is the ONLY execution entry point."""
        agent_id = f"core_{agent_type}"
        worker = self.runtime.get(agent_id)
        if not worker:
            raise RuntimeError(
                f"Agent {agent_id} not found in runtime. "
                f"Ensure AgentRuntime.initialize() was called at startup."
            )
        return worker.agent_instance

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
        cached = await short_term_memory.get_context(str(context.task_id))
        if cached:
            context.context.update(cached)
        recent_tasks = await task_repo.list_by_user(context.user_id, limit=3)
        if recent_tasks:
            context.context["recent_tasks"] = [
                {"query": t.query, "status": t.status, "result_summary": str(t.result)[:200] if t.result else None}
                for t in recent_tasks if t.id != str(context.task_id)
            ]
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

    async def _execute_with_retry(self, agent, input_data: AgentInput) -> AgentOutput:
        async def _execute():
            return await agent.execute(input_data)
        try:
            return await retry_with_backoff(_execute, self.retry_config)
        except Exception as e:
            logger.error(f"Agent execution failed after retries: {e}")
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
        context.result = combined_result
        context.status = TaskStatus.COMPLETED
        await self._save_task_state(context)
        await short_term_memory.save_context(str(context.task_id), context.context, expire=1800)
        await trace_repo.update_status(context.trace_id, TaskStatus.COMPLETED.value)

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

        from .modes import ModeStrategyFactory
        strategy = ModeStrategyFactory.get(mode)
        return await strategy.execute(self.runtime, self, query, config, task_id, user_id)

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
