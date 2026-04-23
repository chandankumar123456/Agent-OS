from typing import Dict, Any
from uuid import UUID
from ...agents.base import AgentOutput, AgentStatus
from ...logs.logger import logger
from ...memory.long_term import workflow_repo
from .base import ModeStrategy


class WorkflowMode(ModeStrategy):
    """Workflow mode: load a predefined workflow from DB and execute it.

    If no predefined workflow exists for the query, falls back to
    planning a new workflow dynamically (same as TaskMode).
    """

    async def execute(self, runtime, orchestrator, query, config, task_id, user_id):
        logger.info(f"Workflow mode execution for task {task_id}")

        # Attempt to load a predefined workflow by name from config
        workflow_name = config.get("workflow_name")
        if workflow_name:
            predefined = await workflow_repo.get_by_name(workflow_name)
            if predefined:
                logger.info(f"Loaded predefined workflow '{workflow_name}' for task {task_id}")
                # TODO: Execute predefined workflow nodes instead of planning
                # For now, execute via pipeline but mark mode as workflow
                result = await orchestrator._execute_pipeline(query, config, task_id, user_id)
                if result.status == AgentStatus.SUCCESS and result.output_data:
                    result.output_data["mode"] = "workflow"
                    result.output_data["workflow_name"] = workflow_name
                return result

        # Fall back to dynamic planning
        logger.info(f"No predefined workflow found for '{workflow_name}', falling back to dynamic plan")
        result = await orchestrator._execute_pipeline(query, config, task_id, user_id)
        if result.status == AgentStatus.SUCCESS and result.output_data:
            result.output_data["mode"] = "workflow"
        return result
