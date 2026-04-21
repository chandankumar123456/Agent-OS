from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime
import json
from ..agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from ..agents.types import TaskStatus, StepStatus
from ..agents import PlannerAgent, ExecutorAgent, VerifierAgent
from ..logs.logger import logger
from ..logs.tracing import trace_manager
from ..mcp.message import MCPMessage, Payload, Metadata
from ..mcp.protocol import mcp_protocol
from ..memory.long_term import task_repo, step_repo
from ..memory.short_term import short_term_memory
from ..guardrails.validator import guardrails
from ..orchestrator.retry import retry_with_backoff, RetryConfig
from ..orchestrator.fallback import fallback_manager, FallbackAgent
from ..orchestrator.errors import ErrorType, UnrecoverableError
from ..tools.registry import tool_registry
from ..config.settings import settings


class TaskContext:
    def __init__(self, task_id: UUID, query: str, config: Optional[Dict[str, Any]] = None):
        self.task_id = task_id
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
        self.retry_config = RetryConfig(
            max_retries=settings.MAX_RETRIES,
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0
        )
        
        fallback_manager.register_fallback("planner", "planner")
        fallback_manager.register_fallback("executor", "executor")
        fallback_manager.register_fallback("verifier", "verifier")
    
    async def _load_memory(self, context: TaskContext) -> None:
        try:
            cached_context = await short_term_memory.get_context(str(context.task_id))
            if cached_context:
                context.context.update(cached_context)
                logger.info(f"Loaded context from Redis for task {context.task_id}")
            
            db_task = await task_repo.get(str(context.task_id))
            if db_task:
                logger.info(f"Loaded task from DB: {context.task_id}")
        except Exception as e:
            logger.warning(f"Memory load failed, using fresh context: {e}")
    
    async def _save_memory(self, context: TaskContext) -> None:
        try:
            await short_term_memory.save_context(
                str(context.task_id),
                context.context,
                expire=3600
            )
            logger.info(f"Saved context to Redis for task {context.task_id}")
        except Exception as e:
            logger.warning(f"Redis save failed: {e}")
        
        try:
            await task_repo.update(
                str(context.task_id),
                status=context.status.value,
                result=context.result,
                error=str(context.error) if context.error else None
            )
            logger.info(f"Saved task to DB: {context.task_id}")
        except Exception as e:
            logger.warning(f"DB save failed: {e}")
    
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
        async def execute_agent():
            return await agent.execute(input_data)
        
        try:
            return await retry_with_backoff(
                execute_agent,
                self.retry_config
            )
        except Exception as e:
            logger.error(f"All retries exhausted: {e}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="retry_exhausted",
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
    
    async def execute_task(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        task_id: Optional[UUID] = None
    ) -> AgentOutput:
        task_id = task_id or uuid4()
        step_id = uuid4()
        trace_id = str(uuid4())
        
        context = TaskContext(task_id, query, config)
        context.trace_id = trace_id
        
        main_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="task_execution",
            agent_name="orchestrator",
            metadata={"query": query, "task_id": str(task_id)}
        )
        
        logger.info(f"Starting task {task_id} for query: {query}")
        
        try:
            if not await self._validate_input(query, config or {}):
                raise UnrecoverableError(
                    "Input validation failed",
                    ErrorType.VALIDATION_ERROR
                )
            
            await self._load_memory(context)
            
            self._create_mcp_message(
                context=context,
                sender="orchestrator",
                receiver="planner",
                payload={
                    "input_data": {"query": query},
                    "context_snapshot": context.context
                },
                step_id=step_id
            )
            
            tools_schema = tool_registry.list_tools()
            
            plan_input = AgentInput(
                task_id=task_id,
                step_id=step_id,
                role=AgentRole.PLANNER,
                input_data={
                    "query": query,
                    "tools": tools_schema
                },
                context=context.context,
                constraints=config
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
                trace_manager.end_span(main_span, "failure", str(plan_result.error_message))
                return plan_result
            
            steps = plan_result.output_data.get("steps", [])
            if not isinstance(steps, list):
                raise UnrecoverableError("Planner returned invalid steps structure", ErrorType.VALIDATION_ERROR)

            if not all(isinstance(step, dict) and step.get("step") for step in steps):
                raise UnrecoverableError("Planner returned malformed step entries", ErrorType.VALIDATION_ERROR)

            context.steps = steps
            logger.info(f"Generated {len(steps)} steps")
            
            step_results = []
            for i, step in enumerate(steps):
                step_id = uuid4()
                context.current_step = i
                
                step_span = trace_manager.start_span(
                    trace_id=trace_id,
                    operation=f"step_{i}",
                    agent_name="executor",
                    metadata={"step": step}
                )
                
                self._create_mcp_message(
                    context=context,
                    sender="orchestrator",
                    receiver="executor",
                    payload={
                        "input_data": {"step": step.get("step", ""), "step_index": i},
                        "context_snapshot": context.context
                    },
                    step_id=step_id
                )
                
                exec_input = AgentInput(
                    task_id=task_id,
                    step_id=step_id,
                    role=AgentRole.EXECUTOR,
                    input_data={
                        "step": step.get("step", ""),
                        "step_index": i,
                        "tools": tools_schema
                    },
                    context=context.context,
                    constraints=config
                )
                
                try:
                    exec_result = await self._execute_with_fallback(
                        self.executor,
                        self.executor,
                        exec_input,
                        "executor",
                        "executor"
                    )
                except Exception as e:
                    logger.error(f"Step {i} execution error: {e}")
                    exec_result = AgentOutput(
                        task_id=task_id,
                        step_id=step_id,
                        status=AgentStatus.FAILURE,
                        error_type="execution_error",
                        error_message=str(e),
                        recoverable=True
                    )
                
                step_results.append({
                    "step": step,
                    "agent": step.get("agent_type", "executor"),
                    "result": exec_result.output_data,
                    "status": exec_result.status.value,
                    "step_id": str(step_id),
                    "confidence": exec_result.confidence
                })
                
                context.context[f"step_{i}"] = exec_result.output_data
                
                trace_manager.end_span(step_span, "success" if exec_result.status == AgentStatus.SUCCESS else "failure")
                
                if exec_result.status == AgentStatus.FAILURE:
                    logger.warning(f"Step {i} failed: {exec_result.error_message}")
                    if not exec_result.recoverable:
                        break
            
            verify_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="verification",
                agent_name="verifier",
                metadata={"steps": len(step_results)}
            )
            
            self._create_mcp_message(
                context=context,
                sender="orchestrator",
                receiver="verifier",
                payload={
                    "input_data": {"output": step_results},
                    "context_snapshot": context.context
                },
                step_id=step_id
            )
            
            valid_input = AgentInput(
                task_id=task_id,
                step_id=uuid4(),
                role=AgentRole.VERIFIER,
                input_data={"output": step_results},
                context=context.context
            )
            
            verify_result = await self._execute_with_fallback(
                self.verifier,
                self.verifier,
                valid_input,
                "verifier",
                "verifier"
            )
            
            trace_manager.end_span(verify_span, "success" if verify_result.status == AgentStatus.SUCCESS else "failure")
            
            combined_result = {
                "query": query,
                "steps": step_results,
                "verified": verify_result.output_data.get("valid", True),
                "verification": verify_result.output_data,
                "trace_id": trace_id
            }
            
            if not await self._validate_output(combined_result):
                logger.warning("Final output validation failed")
            
            context.result = combined_result
            
            await self._save_memory(context)
            
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
                    f"Trace: {trace_id}"
                ]
            )
            
        except UnrecoverableError as e:
            logger.error(f"Unrecoverable error: {e}")
            context.error = str(e)
            await self._save_memory(context)
            trace_manager.end_span(main_span, "failure", str(e))
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type=e.error_type.value,
                error_message=str(e),
                recoverable=False
            )
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            context.error = str(e)
            await self._save_memory(context)
            trace_manager.end_span(main_span, "failure", str(e))
            return AgentOutput(
                task_id=task_id,
                step_id=uuid4(),
                status=AgentStatus.FAILURE,
                error_type="task_execution_error",
                error_message=str(e),
                recoverable=True
            )
    
    async def run_workflow(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        result = await self.execute_task(query, config)
        return result.output_data


orchestrator = Orchestrator()
