from typing import Dict, Any
from uuid import UUID
from ...agents.base import AgentOutput, AgentStatus, AgentInput, AgentRole
from ...agents.types import TaskStatus
from ...logs.logger import logger
from ...logs.tracing import trace_manager
from ...memory.long_term import task_repo
from ...mcp.protocol import mcp_protocol
from .base import ModeStrategy


class CollaborationMode(ModeStrategy):
    """Collaboration mode: planner assigns steps to different registered agents.

    Steps are distributed via MCP messages to agent workers.
    """

    async def execute(self, runtime, orchestrator, query, config, task_id, user_id):
        trace_id = orchestrator._new_trace_id()
        context = orchestrator._create_task_context(task_id, user_id, query, config)
        context.trace_id = trace_id

        await task_repo.update(str(task_id), status=TaskStatus.RUNNING.value)

        main_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="collaboration_execution",
            agent_name="orchestrator",
            metadata={"query": query, "task_id": str(task_id)}
        )

        # Plan with varying agent_types via Runtime
        plan_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="planning",
            agent_name="planner",
            metadata={}
        )

        plan_input = AgentInput(
            task_id=task_id,
            step_id=UUID(int=0),
            role=AgentRole.PLANNER,
            input_data={"query": query, "mode": "collaboration"},
            context={"query": query},
            constraints=config,
        )
        planner_worker = runtime.get("core_planner")
        plan_result = await orchestrator._execute_with_retry(planner_worker.agent_instance, plan_input, role="planner")

        trace_manager.end_span(plan_span, "success" if plan_result.status == AgentStatus.SUCCESS else "failure")
        await trace_manager.persist_span(plan_span)

        if plan_result.status != AgentStatus.SUCCESS:
            trace_manager.end_span(main_span, "failure", plan_result.error_message)
            await trace_manager.persist_trace(trace_id)
            return plan_result

        steps = plan_result.output_data.get("steps", [])
        step_results = []

        for idx, step in enumerate(steps):
            agent_type = step.get("agent_type", "executor")

            # Resolve agent via Router with fallback support
            worker = orchestrator.router.resolve_worker(agent_type)
            agent_id = worker.agent_id if hasattr(worker, "agent_id") else f"core_{agent_type}"
            if not worker:
                logger.warning(f"Collaboration mode: agent for role '{agent_type}' not found, falling back to core_executor")
                worker = runtime.get("core_executor")
                agent_id = "core_executor"

            exec_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="execution",
                agent_name=agent_id,
                metadata={"step": idx}
            )

            # Send MCP message to the agent worker
            message = mcp_protocol.create_message(
                task_id=task_id,
                sender="orchestrator",
                receiver=agent_id,
                payload={
                    "input_data": {
                        "step": step.get("step", ""),
                        "step_number": idx + 1,
                    },
                },
                step_id=UUID(int=idx),
            )
            await mcp_protocol.send_message(message)

            # Also execute directly for result collection
            # (MCP message goes to inbox; direct execute gets result)
            exec_input = AgentInput(
                task_id=task_id,
                step_id=UUID(int=idx),
                role=AgentRole.EXECUTOR,
                input_data={"step": step.get("step", ""), "step_number": idx + 1},
                context={"query": query, "previous_results": step_results},
                constraints=config,
            )
            exec_result = await orchestrator._execute_with_retry(worker.agent_instance, exec_input, role=agent_type)

            trace_manager.end_span(exec_span, "success" if exec_result.status == AgentStatus.SUCCESS else "failure")
            await trace_manager.persist_span(exec_span)

            step_results.append({
                "step_id": str(idx),
                "step_number": idx + 1,
                "agent_type": agent_type,
                "status": "completed" if exec_result.status == AgentStatus.SUCCESS else "failed",
                "output_data": exec_result.output_data,
            })

        # Verify via Runtime
        verify_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="verification",
            agent_name="verifier",
            metadata={"steps": len(step_results)}
        )

        verify_input = AgentInput(
            task_id=task_id,
            step_id=UUID(int=len(steps)),
            role=AgentRole.VERIFIER,
            input_data={"output": step_results, "query": query},
            context={"steps": step_results},
        )
        verifier_worker = runtime.get("core_verifier")
        verify_result = await orchestrator._execute_with_retry(verifier_worker.agent_instance, verify_input, role="verifier")

        trace_manager.end_span(verify_span, "success" if verify_result.status == AgentStatus.SUCCESS else "failure")
        await trace_manager.persist_span(verify_span)

        combined_result = {
            "query": query,
            "steps": step_results,
            "mode": "collaboration",
            "trace_id": trace_id,
            "verified": verify_result.output_data.get("valid", True) if verify_result.status == AgentStatus.SUCCESS else False,
        }

        await orchestrator._save_final_state(context, combined_result, verify_result)
        trace_manager.end_span(main_span, "success")
        await trace_manager.persist_trace(trace_id)

        return AgentOutput(
            task_id=task_id,
            step_id=UUID(int=len(steps)),
            status=AgentStatus.SUCCESS,
            output_data=combined_result,
            confidence=verify_result.confidence if verify_result.status == AgentStatus.SUCCESS else 0.5,
        )
