from typing import Dict, Any
from uuid import UUID
from ..agents.base import AgentInput, AgentStatus, AgentRole
from ..agents.types import StepStatus
from ..memory.long_term import workflow_node_repo, node_trace_repo
from ..logs.tracing import trace_manager
from ..logs.logger import logger
from ..orchestrator.errors import UnrecoverableError, ErrorType, WorkflowPausedForApproval


class StepExecutor:
    """Executes individual workflow steps through the Runtime."""

    @staticmethod
    def _status_label(value) -> str:
        return value.lower() if isinstance(value, str) else str(value)

    async def execute(
        self,
        task_id: UUID,
        trace_id: str,
        context,
        step_row: Dict[str, Any],
        tools_schema: list,
        config: Dict[str, Any],
        agent_instance,
    ) -> Dict[str, Any]:
        step_id = step_row["step_id"]
        step_number = step_row["step_number"]
        node_type = step_row.get("node_type", "agent")

        if node_type == "wait":
            # Check if this node was already approved/rejected in DB (resume scenario)
            node = await workflow_node_repo.get_by_id(step_id)
            if node and node.status == StepStatus.APPROVED.value:
                # Treat as a normal execution node on resume
                pass
            elif node and node.status == StepStatus.REJECTED.value:
                raise UnrecoverableError(
                    "Workflow node was previously rejected",
                    ErrorType.VALIDATION_ERROR,
                )
            else:
                await workflow_node_repo.update(step_id, status=StepStatus.WAITING_APPROVAL.value)
                raise WorkflowPausedForApproval(str(step_id), step_row.get("approval_config"))

        await workflow_node_repo.update(step_id, status=StepStatus.RUNNING.value)

        step_span = trace_manager.start_span(
            trace_id=trace_id,
            operation=f"step_{step_number}",
            agent_name=step_row.get("agent_type", "executor"),
            metadata={"step_number": step_number},
        )

        step_input = step_row.get("input_data", {})
        allowed_tools = getattr(agent_instance, "allowed_tools", None)
        exec_input = AgentInput(
            task_id=task_id,
            step_id=UUID(step_id) if isinstance(step_id, str) else step_id,
            role=AgentRole.EXECUTOR,
            input_data={
                "step": step_input.get("step", ""),
                "step_number": step_number,
                "tools": tools_schema,
            },
            context=dict(context.context),
            constraints=config,
            allowed_tools=allowed_tools,
        )

        try:
            exec_result = await agent_instance.execute(exec_input)

            if exec_result.status != AgentStatus.SUCCESS:
                await workflow_node_repo.update(
                    step_id,
                    status=self._status_label(StepStatus.FAILED.value),
                    output_data=exec_result.output_data,
                    confidence=exec_result.confidence
                )
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

            await workflow_node_repo.update(
                step_id,
                status=self._status_label(StepStatus.COMPLETED.value),
                output_data=exec_result.output_data,
                confidence=exec_result.confidence
            )
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
            await workflow_node_repo.update(
                step_id,
                status=self._status_label(StepStatus.FAILED.value),
                output_data={"error": str(e)}
            )
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
