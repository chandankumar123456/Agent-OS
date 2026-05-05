from typing import Dict, Any
from uuid import UUID
from ...agents.base import AgentOutput, AgentStatus, AgentInput, AgentRole
from ...agents.types import TaskStatus
from ..errors import ErrorType, ErrorCode, UnrecoverableError
from ...logs.logger import logger
from ...logs.tracing import trace_manager
from ...memory.long_term import task_repo
from .base import ModeStrategy


class AutonomousMode(ModeStrategy):
    """Autonomous mode: agent loop that executes, evaluates, and decides to continue/halt/replan.

    Each planning and execution step delegates to AgentRuntime.
    """

    async def execute(self, runtime, orchestrator, query, config, task_id, user_id):
        max_steps = config.get("max_steps", 10)
        trace_id = orchestrator._new_trace_id()
        context = orchestrator._create_task_context(task_id, user_id, query, config)
        context.trace_id = trace_id

        await task_repo.update(str(task_id), status=TaskStatus.RUNNING.value)

        main_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="autonomous_execution",
            agent_name="orchestrator",
            metadata={"query": query, "task_id": str(task_id)}
        )

        step_results = []
        current_query = query

        for step_num in range(max_steps):
            logger.info(f"Autonomous step {step_num + 1}/{max_steps} for task {task_id}")

            plan_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="planning",
                agent_name="planner",
                metadata={"step": step_num}
            )

            # Plan a single step via Runtime
            plan_input = AgentInput(
                task_id=task_id,
                step_id=UUID(int=step_num),
                role=AgentRole.PLANNER,
                input_data={"query": current_query, "mode": "autonomous"},
                context={"step": step_num, "previous_results": step_results},
                constraints=config,
            )
            planner_worker = runtime.get("core_planner")
            if not planner_worker:
                raise UnrecoverableError(
                    "core_planner not available in runtime",
                    ErrorType.SYSTEM_ERROR,
                    ErrorCode.INTERNAL_ERROR
                )
            plan_result = await orchestrator._execute_with_retry(planner_worker.agent_instance, plan_input, role="planner")

            trace_manager.end_span(plan_span, "success" if plan_result.status == AgentStatus.SUCCESS else "failure")
            await trace_manager.persist_span(plan_span)

            if plan_result.status != AgentStatus.SUCCESS:
                logger.error(f"Autonomous planning failed at step {step_num + 1}")
                break

            steps = plan_result.output_data.get("steps", [])
            if not steps:
                logger.info(f"Autonomous mode: planner returned no more steps at {step_num + 1}")
                break

            step = steps[0]

            exec_span = trace_manager.start_span(
                trace_id=trace_id,
                operation="execution",
                agent_name="executor",
                metadata={"step": step_num}
            )

            # Execute the step via Runtime
            exec_input = AgentInput(
                task_id=task_id,
                step_id=UUID(int=step_num),
                role=AgentRole.EXECUTOR,
                input_data={"step": step.get("step", ""), "step_number": step_num + 1},
                context={"query": current_query, "previous_results": step_results},
                constraints=config,
            )
            executor_worker = runtime.get("core_executor")
            if not executor_worker:
                raise UnrecoverableError(
                    "core_executor not available in runtime",
                    ErrorType.SYSTEM_ERROR,
                    ErrorCode.INTERNAL_ERROR
                )
            exec_result = await orchestrator._execute_with_retry(executor_worker.agent_instance, exec_input, role="executor")

            trace_manager.end_span(exec_span, "success" if exec_result.status == AgentStatus.SUCCESS else "failure")
            await trace_manager.persist_span(exec_span)

            if exec_result.status != AgentStatus.SUCCESS:
                logger.error(f"Autonomous execution failed at step {step_num + 1}")
                step_results.append({"step": step_num + 1, "status": "failed", "error": exec_result.error_message})
                break

            step_results.append({
                "step": step_num + 1,
                "status": "completed",
                "output": exec_result.output_data,
            })

            # Evaluate if task is complete
            if orchestrator._is_task_complete(exec_result.output_data):
                logger.info(f"Autonomous mode: task complete at step {step_num + 1}")
                break

            # Update query for next iteration
            current_query = f"Previous result: {exec_result.output_data}. Original task: {query}"

        # Verify final results via Runtime
        verify_span = trace_manager.start_span(
            trace_id=trace_id,
            operation="verification",
            agent_name="verifier",
            metadata={"steps": len(step_results)}
        )

        verify_input = AgentInput(
            task_id=task_id,
            step_id=UUID(int=max_steps),
            role=AgentRole.VERIFIER,
            input_data={"output": step_results, "query": query},
            context={"steps": step_results},
        )
        verifier_worker = runtime.get("core_verifier")
        if not verifier_worker:
            raise UnrecoverableError(
                "core_verifier not available in runtime",
                ErrorType.SYSTEM_ERROR,
                ErrorCode.INTERNAL_ERROR
            )
        verify_result = await orchestrator._execute_with_retry(verifier_worker.agent_instance, verify_input, role="verifier")

        trace_manager.end_span(verify_span, "success" if verify_result.status == AgentStatus.SUCCESS else "failure")
        await trace_manager.persist_span(verify_span)

        combined_result = {
            "query": query,
            "steps": step_results,
            "mode": "autonomous",
            "trace_id": trace_id,
            "verified": verify_result.output_data.get("valid", True) if verify_result.status == AgentStatus.SUCCESS else False,
        }

        await orchestrator._save_final_state(context, combined_result, verify_result)
        trace_manager.end_span(main_span, "success")
        await trace_manager.persist_trace(trace_id)

        return AgentOutput(
            task_id=task_id,
            step_id=UUID(int=max_steps),
            status=AgentStatus.SUCCESS,
            output_data=combined_result,
            confidence=verify_result.confidence if verify_result.status == AgentStatus.SUCCESS else 0.5,
        )
