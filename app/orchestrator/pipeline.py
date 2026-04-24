from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from ..agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from ..agents.types import TaskStatus, StepStatus
from ..logs.logger import logger
from ..logs.tracing import trace_manager
from ..memory.long_term import task_repo, trace_repo, node_trace_repo, workflow_node_repo
from ..memory.short_term import short_term_memory
from ..guardrails.validator import guardrails
from ..orchestrator.retry import retry_with_backoff, RetryConfig, is_retryable
from ..orchestrator.errors import ErrorType, UnrecoverableError, WorkflowPausedForApproval
from ..tools.registry import tool_registry
from .workflow import WorkflowEngine, WorkflowNode
from .builder import WorkflowBuilder
from .executor import StepExecutor


class PipelineExecutor:
    """Executes the plan → execute → verify pipeline for task and workflow modes."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.workflow_engine = WorkflowEngine()
        self.workflow_builder = WorkflowBuilder()
        self.step_executor = StepExecutor()
        self.retry_config = orchestrator.retry_config

    @staticmethod
    def _status_label(value) -> str:
        return value.lower() if isinstance(value, str) else str(value)

    async def execute(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        task_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
    ) -> AgentOutput:
        from ..orchestrator.core import TaskContext

        task_id = task_id or uuid4()
        if not user_id:
            user_id = "system"
        config = config or {}

        trace_id = self.orchestrator._new_trace_id()
        context = TaskContext(task_id, user_id, query, config)
        context.trace_id = trace_id

        try:
            await trace_repo.create(str(task_id), trace_id, user_id, status=TaskStatus.RUNNING.value)
        except Exception as e:
            logger.warning(f"Trace row creation failed, continuing with live cache: {e}")

        main_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="task_execution",
            agent_name="orchestrator",
            metadata={"query": query, "task_id": str(task_id)}
        )

        logger.info(f"Starting task {task_id} for query: {query}")

        try:
            if not await self.orchestrator._validate_input(query, config):
                raise UnrecoverableError("Input validation failed", ErrorType.VALIDATION_ERROR)

            await task_repo.update(str(task_id), status=TaskStatus.RUNNING.value)
            await trace_repo.update_status(trace_id, TaskStatus.RUNNING.value)
            await self.orchestrator._load_task_state(context)
            await self.orchestrator._hydrate_memory_context(context)

            tools_schema = tool_registry.list_tools()

            plan_input = AgentInput(
                task_id=task_id,
                step_id=uuid4(),
                role=AgentRole.PLANNER,
                input_data={"query": query, "tools": tools_schema, "mode": context.mode},
                context=context.context,
                constraints=config,
            )

            plan_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="planning",
                agent_name="planner",
                metadata={"query": query}
            )

            plan_result = await self.orchestrator._execute_with_retry(
                self.orchestrator._get_agent("planner"), plan_input, role="planner"
            )

            trace_manager.end_span(plan_span, "success" if plan_result.status == AgentStatus.SUCCESS else "failure")
            await trace_manager.persist_span(plan_span)

            if plan_result.status != AgentStatus.SUCCESS:
                await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=plan_result.error_message)
                await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
                trace_manager.end_span(main_span, "failure", str(plan_result.error_message))
                await trace_manager.persist_trace(trace_id)
                return plan_result

            steps = plan_result.output_data.get("steps", [])
            if not isinstance(steps, list):
                raise UnrecoverableError("Planner returned invalid steps structure", ErrorType.VALIDATION_ERROR)
            if not all(isinstance(step, dict) and step.get("step") for step in steps):
                raise UnrecoverableError("Planner returned malformed step entries", ErrorType.VALIDATION_ERROR)

            for step in steps:
                step["user_id"] = user_id
            workflow_state = await self.workflow_builder.build(task_id, user_id, steps)
            workflow = workflow_state["workflow"]
            workflow_nodes = workflow_state["nodes"]

            # Build mapping from planner step ID -> DB node UUID
            planner_id_to_db_id: Dict[str, str] = {}
            for node in workflow_nodes:
                raw_step = (node.input_data or {}).get("raw_step", {})
                planner_id = str(raw_step.get("id", node.step_number))
                planner_id_to_db_id[planner_id] = str(node.id)

            # Convert SQLAlchemy model rows to WorkflowNode dataclass for the engine
            workflow_node_graph: List[WorkflowNode] = [
                WorkflowNode(
                    id=str(node.id),
                    step=str(node.input_data.get("step", "")) if node.input_data else "",
                    agent_type=str(node.agent_type or "executor"),
                    depends_on=[
                        planner_id_to_db_id.get(dep, dep)
                        for dep in (node.depends_on or [])
                    ],
                    condition=str(node.condition_code) if node.condition_code else None,
                    step_number=int(node.step_number or 0),
                    node_type=str(node.node_type or "agent"),
                    approval_config=node.approval_config,
                )
                for node in workflow_nodes
            ]

            context.steps = [
                {
                    "step_id": node.id,
                    "task_id": str(task_id),
                    "step_number": node.step_number,
                    "agent_type": node.agent_type,
                    "depends_on": node.depends_on or [],
                    "input_data": node.input_data or {},
                    "node_type": str(node.node_type or "agent"),
                    "approval_config": node.approval_config,
                }
                for node in workflow_nodes
            ]
            logger.info(f"Generated {len(workflow_nodes)} persisted workflow nodes")

            async def run_node(node, running_context):
                node_row = next(item for item in workflow_nodes if item.id == node.id)
                agent_instance = self.orchestrator.router.resolve(node.agent_type) or self.orchestrator._get_agent("executor")
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
                await workflow_node_repo.update(
                    node_row.id,
                    status=result["status"],
                    output_data=result.get("output_data"),
                    confidence=result.get("confidence")
                )
                return result

            try:
                workflow_result = await self.workflow_engine.execute_graph(
                    workflow_node_graph,
                    {"run_node": run_node},
                    context.context
                )
            except WorkflowPausedForApproval as pause:
                logger.info(f"Workflow paused for approval at node {pause.node_id}")
                await task_repo.update(str(task_id), status=TaskStatus.WAITING_APPROVAL.value)
                await trace_repo.update_status(trace_id, TaskStatus.WAITING_APPROVAL.value)
                trace_manager.end_span(main_span, "paused", f"Waiting approval at node {pause.node_id}")
                await trace_manager.persist_trace(trace_id)
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

            step_results: List[Dict[str, Any]] = []
            for node_id, node_result in workflow_result["nodes"].items():
                step_results.append({
                    "step_id": node_id,
                    "status": node_result["status"],
                    "output_data": node_result.get("output"),
                })

            for node_id, node_result in workflow_result["nodes"].items():
                if node_result["status"] == "skipped":
                    await workflow_node_repo.update(node_id, status=self._status_label(StepStatus.SKIPPED.value))
                    await node_trace_repo.create(
                        task_id=str(task_id),
                        user_id=user_id,
                        trace_id=trace_id,
                        node_id=node_id,
                        status=self._status_label(StepStatus.SKIPPED.value),
                        input_data=next((node.input_data for node in workflow_nodes if node.id == node_id), {}),
                    )

            verify_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="verification",
                agent_name="verifier",
                metadata={"steps": len(step_results)}
            )

            valid_input = AgentInput(
                task_id=task_id,
                step_id=uuid4(),
                role=AgentRole.VERIFIER,
                input_data={"output": step_results},
                context=context.context,
            )

            verify_result = await self.orchestrator._execute_with_retry(
                self.orchestrator._get_agent("verifier"), valid_input, role="verifier"
            )

            trace_manager.end_span(verify_span, "success" if verify_result.status == AgentStatus.SUCCESS else "failure")
            await trace_manager.persist_span(verify_span)

            if verify_result.status != AgentStatus.SUCCESS:
                await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=verify_result.error_message)
                await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
                trace_manager.end_span(main_span, "failure", str(verify_result.error_message))
                await trace_manager.persist_trace(trace_id)
                return verify_result

            combined_result = {
                "query": query,
                "steps": step_results,
                "workflow": {
                    "workflow_id": workflow.id,
                    "definition": workflow.definition,
                    "nodes": workflow_result["nodes"],
                    "edges": workflow_result["edges"],
                },
                "workflow_state": self.orchestrator._serialize_workflow_state(
                    await self.orchestrator._get_workflow_state(task_id)
                ),
                "verified": verify_result.output_data.get("valid", True),
                "verification": verify_result.output_data,
                "trace_id": trace_id,
                "mode": context.mode,
            }

            if not await self.orchestrator._validate_output(combined_result):
                raise UnrecoverableError("Output validation failed", ErrorType.VALIDATION_ERROR)

            context.result = combined_result
            context.status = TaskStatus.COMPLETED
            await self.orchestrator._save_task_state(context)
            await short_term_memory.save_context(str(task_id), context.context, expire=1800)
            await trace_repo.update_status(trace_id, TaskStatus.COMPLETED.value)
            trace_manager.end_span(main_span, "success")
            await trace_manager.persist_trace(trace_id)

            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data=combined_result,
                confidence=verify_result.confidence,
                reasoning_trace=[
                    f"Completed {len(step_results)} steps",
                    f"Verified: {verify_result.output_data.get('valid', True)}",
                    f"Trace: {trace_id}",
                    f"Mode: {context.mode}",
                ],
            )

        except UnrecoverableError as e:
            logger.error(f"Unrecoverable error: {e}")
            context.error = str(e)
            context.status = TaskStatus.FAILED
            await self.orchestrator._save_task_state(context)
            await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=str(e))
            await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
            trace_manager.end_span(main_span, "failure", str(e))
            await trace_manager.persist_trace(trace_id)
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type=e.error_type.value,
                error_message=str(e),
                recoverable=False,
            )
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            context.error = str(e)
            context.status = TaskStatus.FAILED
            await self.orchestrator._save_task_state(context)
            await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=str(e))
            await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
            trace_manager.end_span(main_span, "failure", str(e))
            await trace_manager.persist_trace(trace_id)
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type="task_execution_error",
                error_message=str(e),
                recoverable=is_retryable(e, self.retry_config),
            )
