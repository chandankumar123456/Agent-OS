from typing import Dict, Any
from uuid import UUID
from ...agents.base import AgentOutput, AgentStatus, AgentInput, AgentRole
from ...agents.types import TaskStatus
from ...logs.logger import logger
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

        step_results = []
        current_query = query

        for step_num in range(max_steps):
            logger.info(f"Autonomous step {step_num + 1}/{max_steps} for task {task_id}")

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
            plan_result = await orchestrator._execute_with_retry(planner_worker.agent_instance, plan_input)

            if plan_result.status != AgentStatus.SUCCESS:
                logger.error(f"Autonomous planning failed at step {step_num + 1}")
                break

            steps = plan_result.output_data.get("steps", [])
            if not steps:
                logger.info(f"Autonomous mode: planner returned no more steps at {step_num + 1}")
                break

            step = steps[0]

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
            exec_result = await orchestrator._execute_with_retry(executor_worker.agent_instance, exec_input)

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
        verify_input = AgentInput(
            task_id=task_id,
            step_id=UUID(int=max_steps),
            role=AgentRole.VERIFIER,
            input_data={"output": step_results, "query": query},
            context={"steps": step_results},
        )
        verifier_worker = runtime.get("core_verifier")
        verify_result = await orchestrator._execute_with_retry(verifier_worker.agent_instance, verify_input)

        combined_result = {
            "query": query,
            "steps": step_results,
            "mode": "autonomous",
            "verified": verify_result.output_data.get("valid", True) if verify_result.status == AgentStatus.SUCCESS else False,
        }

        await orchestrator._save_final_state(context, combined_result, verify_result)

        return AgentOutput(
            task_id=task_id,
            step_id=UUID(int=max_steps),
            status=AgentStatus.SUCCESS,
            output_data=combined_result,
            confidence=verify_result.confidence if verify_result.status == AgentStatus.SUCCESS else 0.5,
        )
