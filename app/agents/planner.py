from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any
from .llm_client import llm_client
from ..logs.logger import logger


PLANNER_PROMPT = """You are a Planner agent for Agent-OS. Your role is to break down user queries into executable steps.

Given a user query, analyze it and create a step-by-step plan. Each step should be:
- Clear and actionable
- Independent where possible
- Ordered logically

Return your response as a JSON array of step objects:
[
  {{"step": "step_description", "agent_type": "executor", "depends_on": []}}
]

Query to process: {query}

Respond with only the JSON array."""


class PlannerAgent:
    name: str = "planner"
    role: AgentRole = AgentRole.PLANNER

    def _normalize_plan_response(self, result: Any) -> List[Dict[str, Any]]:
        if result is None:
            return [{"step": "analyze query", "agent_type": "executor", "depends_on": []}]

        if isinstance(result, dict):
            if "steps" in result and isinstance(result["steps"], list):
                result = result["steps"]
            else:
                result = [result]

        if not isinstance(result, list):
            raise ValueError("Planner output must be a list or wrapped steps object")

        steps: List[Dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                raise ValueError("Each planner step must be an object")
            step_name = item.get("step") or item.get("result")
            if not step_name:
                raise ValueError("Planner step missing 'step'")
            normalized = {
                "step": step_name,
                "agent_type": item.get("agent_type", "executor"),
                "depends_on": item.get("depends_on", []),
            }
            steps.append(normalized)

        return steps
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        query = input_data.input_data.get("query", "")
        
        logger.info(f"Planner executing for query: {query}")
        
        messages = [
            {"role": "system", "content": PLANNER_PROMPT.format(query=query)}
        ]
        
        try:
            result = await llm_client.complete_json(messages)
            steps = self._normalize_plan_response(result)
            
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.SUCCESS,
                output_data={
                    "steps": steps,
                    "total_steps": len(steps)
                },
                confidence=0.9,
                reasoning_trace=[
                    f"Analyzed query: {query}",
                    f"Generated {len(steps)} steps",
                    "Plan ready for execution"
                ]
            )
        except Exception as e:
            logger.error(f"Planner failed: {e}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="planning_error",
                error_message=str(e),
                recoverable=True
            )
