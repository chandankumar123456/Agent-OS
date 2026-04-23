from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any
from .llm_client import llm_client
from ..logs.logger import logger


PLANNER_PROMPT = """You are a workflow planner for Agent-OS. Your task is to generate a VALID execution plan as a directed acyclic graph (DAG).

STRICT RULES (must be followed exactly):

1. Node Structure:
   - Each step object MUST have:
     * "id" (string, unique within the plan, e.g., "step_1", "step_2")
     * "step" (clear action description)
     * "agent_type" (always "executor")
     * "depends_on" (list of node IDs this step depends on)

2. Dependency Rules:
   - A node can ONLY depend on nodes that EXIST in the same output.
   - NEVER reference a node that is not defined.
   - NEVER use natural language in "depends_on".
     ❌ "Rank the ingredients by cost"
     ✅ "step_1"

3. Graph Rules:
   - Must be a valid DAG (no cycles).
   - No missing dependencies.
   - No forward references to undefined nodes.
   - Each dependency must point to an earlier node ID.

4. Minimality:
   - Generate only necessary steps.
   - Avoid over-decomposition.
   - If the task is simple, use 1 node with empty depends_on.

5. Consistency:
   - IDs must be consistent and reused correctly.
   - No duplicate IDs.
   - All dependencies must match EXACT node IDs.

EXAMPLE (valid):
[
  {{"id": "step_1", "step": "Find cheapest healthy breakfast ingredients", "agent_type": "executor", "depends_on": []}},
  {{"id": "step_2", "step": "Rank ingredients by cost-effectiveness and nutrition", "agent_type": "executor", "depends_on": ["step_1"]}}
]

Query to process: {query}

Return ONLY valid JSON. No explanation."""


class PlannerAgent:
    name: str = "planner"
    role: AgentRole = AgentRole.PLANNER

    def _normalize_plan_response(self, result: Any) -> List[Dict[str, Any]]:
        if result is None:
            return [{"id": "step_1", "step": "analyze query", "agent_type": "executor", "depends_on": []}]

        if isinstance(result, dict):
            if "steps" in result and isinstance(result["steps"], list):
                result = result["steps"]
            elif "nodes" in result and isinstance(result["nodes"], list):
                result = result["nodes"]
            else:
                result = [result]

        if not isinstance(result, list):
            raise ValueError("Planner output must be a list or wrapped steps/nodes object")

        steps: List[Dict[str, Any]] = []
        for index, item in enumerate(result, start=1):
            if not isinstance(item, dict):
                raise ValueError("Each planner step must be an object")
            step_name = item.get("step") or item.get("task") or item.get("result")
            if not step_name:
                raise ValueError("Planner step missing 'step'")
            step_id = str(item.get("id", f"step_{index}"))
            normalized = {
                "id": step_id,
                "step": step_name,
                "agent_type": item.get("agent_type", "executor"),
                "depends_on": item.get("depends_on", []),
            }
            steps.append(normalized)

        # Validate and sanitize dependencies
        valid_ids = {step["id"] for step in steps}
        for step in steps:
            raw_deps = step["depends_on"]
            if not isinstance(raw_deps, list):
                raw_deps = [raw_deps] if raw_deps else []
            sanitized = []
            for dep in raw_deps:
                dep_id = str(dep) if dep is not None else ""
                if dep_id in valid_ids:
                    sanitized.append(dep_id)
                else:
                    logger.warning(
                        f"Planner generated invalid dependency '{dep_id}' for step '{step['id']}'. "
                        f"Stripping it. Valid IDs: {valid_ids}"
                    )
            step["depends_on"] = sanitized

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
