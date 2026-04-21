from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime
import json
import asyncio
from ..agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from ..agents.types import TaskStatus, StepStatus
from ..agents import PlannerAgent, ExecutorAgent, VerifierAgent
from ..logs.logger import logger
from ..logs.tracing import trace_manager
from ..mcp.message import MCPMessage, Payload, Metadata
from ..mcp.protocol import mcp_protocol
from ..memory.long_term import task_repo, trace_repo, node_trace_repo, workflow_repo, workflow_node_repo, workflow_edge_repo
from ..guardrails.validator import guardrails
from ..orchestrator.retry import retry_with_backoff, RetryConfig
from ..orchestrator.fallback import fallback_manager, FallbackAgent
from ..orchestrator.errors import ErrorType, UnrecoverableError
from ..tools.registry import tool_registry
from ..config.settings import settings
from .workflow import WorkflowEngine


class TaskContext:
    def __init__(self, task_id: UUID, user_id: str, query: str, config: Optional[Dict[str, Any]] = None):
        self.task_id = task_id
        self.user_id = user_id
        self.query = query
        self.config = config or {}
        self.status = TaskStatus.PENDING
        self.steps: List[Dict[str, Any]] = []
        self.context = {"query": query}
        self.result = None
        self.error = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.current_step = 0
        self.trace_id = str(uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "user_id": self.user_id,
            "query": self.query,
            "status": self.status.value,
            "steps": self.steps,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class Orchestrator:
    def __init__(self):
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()
        self.verifier = VerifierAgent()
        self.workflow_engine = WorkflowEngine()
        self.retry_config = RetryConfig(
            max_retries=settings.MAX_RETRIES,
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0
        )
        
        fallback_manager.register_fallback("planner", "planner")
        fallback_manager.register_fallback("executor", "executor")
        fallback_manager.register_fallback("verifier", "verifier")
    
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
            logger.warning(f"DB save failed: {e}")

    @staticmethod
    def _status_label(status: str) -> str:
        return status.upper() if isinstance(status, str) else str(status)
    
    async def _validate_input(self, query: str, config: Dict[str, Any]) -> bool:
        try:
            validation_result = await guardrails.validator.validate({
                "query": query,
                "config": config
            })
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
    
    def _create_mcp_message(
        self,
        context: TaskContext,
        sender: str,
        receiver: str,
        payload: Dict[str, Any],
        step_id: Optional[UUID] = None
    ) -> MCPMessage:
        return mcp_protocol.create_message(
            task_id=context.task_id,
            sender=sender,
            receiver=receiver,
            payload=payload,
            step_id=step_id
        )
    
    async def _execute_with_retry(
        self,
        agent,
        input_data: AgentInput
    ) -> AgentOutput:
        try:
            return await agent.execute(input_data)
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="execution_error",
                error_message=str(e),
                recoverable=False
            )
    
    async def _execute_with_fallback(
        self,
        primary_agent,
        fallback_agent,
        input_data: AgentInput,
        primary_name: str,
        fallback_name: str
    ) -> AgentOutput:
        fallback = fallback_manager.get_fallback(primary_name)

        if not fallback or fallback_agent is primary_agent:
            return await self._execute_with_retry(primary_agent, input_data)
        
        async def primary_func():
            return await self._execute_with_retry(primary_agent, input_data)
        
        async def fallback_func():
            logger.warning(f"Primary agent {primary_name} failed, using fallback {fallback_name}")
            return await self._execute_with_retry(fallback_agent, input_data)
        
        try:
            return await fallback.execute_with_fallback(
                primary_func,
                fallback_func
            )
        except Exception as e:
            fallback.reset()
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="fallback_exhausted",
                error_message=str(e),
                recoverable=False
            )
    
    async def _run_step(
        self,
        task_id: UUID,
        trace_id: str,
        context: TaskContext,
        step_row: Dict[str, Any],
        tools_schema: List[Dict[str, Any]],
        config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        step_id = step_row["step_id"]
        step_number = step_row["step_number"]

        await workflow_node_repo.update(step_id, status=StepStatus.RUNNING.value)

        step_span = trace_manager.start_span(
            trace_id=trace_id,
            operation=f"step_{step_number}",
            agent_name=step_row.get("agent_type", "executor"),
            metadata={"step_number": step_number},
        )

        step_input = step_row.get("input_data", {})
        exec_input = AgentInput(
            task_id=task_id,
            step_id=UUID(step_id),
            role=AgentRole.EXECUTOR,
            input_data={
                "step": step_input.get("step", ""),
                "step_number": step_number,
                "tools": tools_schema,
            },
            context=dict(context.context),
            constraints=config,
        )

        try:
            exec_result = await self._execute_with_fallback(
                self.executor,
                self.executor,
                exec_input,
                "executor",
                "executor",
            )

            if exec_result.status != AgentStatus.SUCCESS:
                await workflow_node_repo.update(step_id, status=self._status_label(StepStatus.FAILED.value), output_data=exec_result.output_data, confidence=exec_result.confidence)
                await node_trace_repo.create(
                    task_id=str(task_id),
                    user_id=context.user_id,
                    trace_id=trace_id,
                    node_id=step_id,
                    status=self._status_label(StepStatus.FAILED.value),
                    input_data=step_input,
                    output_data=exec_result.output_data,
                    error=exec_result.error_message,
                )
                trace_manager.end_span(step_span, "failure", exec_result.error_message)
                raise UnrecoverableError(
                    exec_result.error_message or "Step execution failed",
                    ErrorType.EXECUTION_ERROR,
                )

            await workflow_node_repo.update(step_id, status=self._status_label(StepStatus.COMPLETED.value), output_data=exec_result.output_data, confidence=exec_result.confidence)
            await node_trace_repo.create(
                task_id=str(task_id),
                user_id=context.user_id,
                trace_id=trace_id,
                node_id=step_id,
                status=self._status_label(StepStatus.COMPLETED.value),
                input_data=step_input,
                output_data=exec_result.output_data,
            )
            trace_manager.end_span(step_span, "success")

            return {
                "step_id": step_id,
                "step_number": step_number,
                "agent_type": step_row.get("agent_type", "executor"),
                "status": StepStatus.COMPLETED.value,
                "output_data": exec_result.output_data,
                "confidence": exec_result.confidence,
            }
        except Exception as e:
            await workflow_node_repo.update(step_id, status=self._status_label(StepStatus.FAILED.value), output_data={"error": str(e)})
            await node_trace_repo.create(
                task_id=str(task_id),
                user_id=context.user_id,
                trace_id=trace_id,
                node_id=step_id,
                status=self._status_label(StepStatus.FAILED.value),
                input_data=step_input,
                output_data={"error": str(e)},
                error=str(e),
            )
            trace_manager.end_span(step_span, "failure", str(e))
            raise

    async def _build_workflow(self, task_id: UUID, user_id: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        definition = {"nodes": steps, "edges": []}
        workflow = await workflow_repo.create(task_id=str(task_id), user_id=user_id, name="planner_workflow", definition=definition)

        node_rows = []
        node_by_step: Dict[str, str] = {}

        for index, step in enumerate(steps, start=1):
            node = await workflow_node_repo.create(
                workflow_id=workflow.id,
                step_number=index,
                agent_type=step.get("agent_type", "executor"),
                depends_on=[str(dep) for dep in step.get("depends_on", []) if dep is not None],
                input_data={"step": step.get("step", ""), "raw_step": step},
                condition_code=step.get("condition"),
            )
            node_rows.append(node)
            node_by_step[str(step.get("id", index))] = node.id

        for step in steps:
            for dep in step.get("depends_on", []):
                dep_id = node_by_step.get(str(dep))
                current_id = node_by_step.get(str(step.get("id")))
                if dep_id and current_id:
                    await workflow_edge_repo.create(workflow.id, dep_id, current_id)

        return {
            "workflow": workflow,
            "nodes": node_rows,
            "definition": definition,
        }

    async def _get_workflow_state(self, task_id: UUID) -> Dict[str, Any]:
        workflow = await workflow_repo.get_by_task(str(task_id))
        if not workflow:
            return {"workflow": None, "nodes": [], "edges": []}

        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        edges = await workflow_edge_repo.get_by_workflow(workflow.id)
        return {
            "workflow": workflow,
            "nodes": nodes,
            "edges": edges,
        }

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
        trace_id = str(uuid4())
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
            if not await self._validate_input(query, config or {}):
                raise UnrecoverableError("Input validation failed", ErrorType.VALIDATION_ERROR)

            await task_repo.update(str(task_id), status=TaskStatus.RUNNING.value)
            await trace_repo.update_status(trace_id, TaskStatus.RUNNING.value)
            await self._load_task_state(context)

            tools_schema = tool_registry.list_tools()

            plan_input = AgentInput(
                task_id=task_id,
                step_id=uuid4(),
                role=AgentRole.PLANNER,
                input_data={"query": query, "tools": tools_schema},
                context=context.context,
                constraints=config,
            )

            plan_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="planning",
                agent_name="planner",
                metadata={"query": query}
            )

            plan_result = await self._execute_with_fallback(
                self.planner,
                self.planner,
                plan_input,
                "planner",
                "planner"
            )

            trace_manager.end_span(plan_span, "success" if plan_result.status == AgentStatus.SUCCESS else "failure")

            if plan_result.status != AgentStatus.SUCCESS:
                await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=plan_result.error_message)
                await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
                trace_manager.end_span(main_span, "failure", str(plan_result.error_message))
                return plan_result

            steps = plan_result.output_data.get("steps", [])
            if not isinstance(steps, list):
                raise UnrecoverableError("Planner returned invalid steps structure", ErrorType.VALIDATION_ERROR)
            if not all(isinstance(step, dict) and step.get("step") for step in steps):
                raise UnrecoverableError("Planner returned malformed step entries", ErrorType.VALIDATION_ERROR)

            for step in steps:
                step["user_id"] = user_id
            workflow_state = await self._build_workflow(task_id, user_id, steps)
            workflow = workflow_state["workflow"]
            workflow_nodes = workflow_state["nodes"]
            context.steps = [
                {
                    "step_id": node.id,
                    "task_id": str(task_id),
                    "step_number": node.step_number,
                    "agent_type": node.agent_type,
                    "depends_on": node.depends_on or [],
                    "input_data": node.input_data or {},
                }
                for node in workflow_nodes
            ]
            logger.info(f"Generated {len(workflow_nodes)} persisted workflow nodes")

            async def run_node(node, running_context):
                node_row = next(item for item in workflow_nodes if item.id == node.id)
                result = await self._run_step(task_id, trace_id, context, {
                    "step_id": node_row.id,
                    "step_number": node_row.step_number,
                    "agent_type": node_row.agent_type,
                    "input_data": node_row.input_data or {},
                }, tools_schema, config)
                await workflow_node_repo.update(node_row.id, status=result["status"], output_data=result.get("output_data"), confidence=result.get("confidence"))
                return result

            workflow_result = await self.workflow_engine.execute_graph(workflow_nodes, {"run_node": run_node}, context.context)
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

            verify_result = await self._execute_with_fallback(
                self.verifier,
                self.verifier,
                valid_input,
                "verifier",
                "verifier"
            )

            trace_manager.end_span(verify_span, "success" if verify_result.status == AgentStatus.SUCCESS else "failure")

            if verify_result.status != AgentStatus.SUCCESS:
                await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=verify_result.error_message)
                await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
                trace_manager.end_span(main_span, "failure", str(verify_result.error_message))
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
                "workflow_state": await self._get_workflow_state(task_id),
                "verified": verify_result.output_data.get("valid", True),
                "verification": verify_result.output_data,
                "trace_id": trace_id,
            }

            if not await self._validate_output(combined_result):
                logger.warning("Final output validation failed")

            context.result = combined_result
            context.status = TaskStatus.COMPLETED
            await self._save_task_state(context)
            await trace_repo.update_status(trace_id, TaskStatus.COMPLETED.value)
            trace_manager.end_span(main_span, "success")

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
                ],
            )

        except UnrecoverableError as e:
            logger.error(f"Unrecoverable error: {e}")
            context.error = str(e)
            context.status = TaskStatus.FAILED
            await self._save_task_state(context)
            await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=str(e))
            await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
            trace_manager.end_span(main_span, "failure", str(e))
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
            await self._save_task_state(context)
            await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error=str(e))
            await trace_repo.update_status(trace_id, TaskStatus.FAILED.value)
            trace_manager.end_span(main_span, "failure", str(e))
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type="task_execution_error",
                error_message=str(e),
                recoverable=True,
            )
    
    async def run_workflow(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        raise UnrecoverableError("Direct workflow execution is disabled", ErrorType.VALIDATION_ERROR)
        return result.output_data


orchestrator = Orchestrator()
