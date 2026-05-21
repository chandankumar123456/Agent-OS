import os
import platform

from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any
from .llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.registry import tool_registry
from ..utils.paths import get_desktop_path as _get_desktop_path
from ..utils.paths import normalize_paths_in_text as _normalize_paths_in_text


PLANNER_PROMPT = """You are a workflow planner for Agent-OS. Your task is to generate a VALID execution plan as a directed acyclic graph (DAG).

STRICT RULES (must be followed exactly):

1. Node Structure:
   - Each step object MUST have:
     * "id" (string, unique within the plan, e.g., "step_1", "step_2")
     * "step" (clear action description — be specific about what tool to use)
     * "step_type" (exactly one of: file_search, file_read, file_write, document_processing, content_generation, browser_open, browser_navigation, desktop_automation, shell_execution, web_search, general)
     * "allowed_tools" (list of exact tool names this step may use)
     * "fallback_tools" (list of exact fallback tool names if primary fails)
     * "expected_output" (what this step should produce)
     * "required" (boolean, true if downstream steps depend on this step succeeding)
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

5. Environment Isolation (CRITICAL):
   - Each step MUST use tools from ONLY ONE execution environment.
   - file_search / file_read / file_write / document_processing / content_generation steps: ONLY filesystem__* and shell__* tools.
   - browser_open / browser_navigation steps: ONLY browser_env__* tools.
   - desktop_automation steps: ONLY desktop_env__* tools.
   - shell_execution steps: ONLY shell__* tools.
   - web_search steps: ONLY cloud__* or web_search tools.
   - NEVER mix browser, desktop, and filesystem tools in the same step.
   - For local file tasks, prefer filesystem tools first. Use desktop tools ONLY as a fallback.
   - NEVER use browser tools to search the local filesystem.

6. Tool Awareness:
   - You have access to the following tools. When a step requires a tool, mention the exact tool name in the step description so the executor knows which one to use.
   - Available tools: {tools}

7. Consistency:
   - IDs must be consistent and reused correctly.
   - No duplicate IDs.
   - All dependencies must match EXACT node IDs.

EXAMPLE (valid):
[
  {{"id": "step_1", "step": "Search filesystem for the major project report", "step_type": "file_search", "allowed_tools": ["filesystem__search_files", "filesystem__list_directory"], "fallback_tools": ["shell__execute_command"], "expected_output": "Path to the report file", "required": true, "agent_type": "executor", "depends_on": []}},
  {{"id": "step_2", "step": "Read the report file", "step_type": "file_read", "allowed_tools": ["filesystem__read_file"], "fallback_tools": [], "expected_output": "Raw content of the report", "required": true, "agent_type": "executor", "depends_on": ["step_1"]}}
]

Current operating system: {os_info}
User home directory: {home_path}
User Desktop path: {desktop_path}

When tasks involve file paths, use the EXACT paths provided above. On Windows use backslashes; on Linux/macOS use forward slashes.

Query to process: {query}

Return ONLY valid JSON. No explanation.
"""


class PlannerAgent:
    name: str = "planner"
    role: AgentRole = AgentRole.PLANNER

    def _normalize_plan_response(
        self,
        result: Any,
        home_path: str = None,
        desktop_path: str = None,
    ) -> List[Dict[str, Any]]:
        if home_path is None:
            home_path = os.path.expanduser("~")
        if desktop_path is None:
            desktop_path = _get_desktop_path()

        if result is None:
            return [{"id": "step_1", "step": "analyze query", "step_type": "general", "allowed_tools": [], "fallback_tools": [], "expected_output": "analysis", "required": False, "agent_type": "executor", "depends_on": []}]

        if isinstance(result, dict):
            if "steps" in result and isinstance(result["steps"], list):
                result = result["steps"]
            elif "nodes" in result and isinstance(result["nodes"], list):
                result = result["nodes"]
            else:
                result = [result]

        if not isinstance(result, list):
            raise ValueError("Planner output must be a list or wrapped steps/nodes object")

        all_tools = tool_registry.list_tools()
        steps: List[Dict[str, Any]] = []
        for index, item in enumerate(result, start=1):
            if not isinstance(item, dict):
                logger.warning(f"Planner step {index} is not a dict, skipping: {item}")
                continue
            step_name = item.get("step") or item.get("task") or item.get("description") or item.get("result") or item.get("action")
            if not step_name:
                step_id = str(item.get("id", f"step_{index}"))
                logger.warning(f"Planner step {step_id} missing name fields, using generic description")
                step_name = f"Execute step {step_id}"
            step_id = str(item.get("id", f"step_{index}"))

            # Normalize hallucinated paths in step text
            step_name = _normalize_paths_in_text(step_name, home_path, desktop_path)

            # Extract structured fields from LLM output (NEVER infer via keyword matching)
            step_type = item.get("step_type", "general")
            allowed_tools = item.get("allowed_tools", [])
            fallback_tools = item.get("fallback_tools", [])
            expected_output = item.get("expected_output", "")
            required = item.get("required", False)

            # Validate that LLM-specified tools actually exist in registry
            registered_names = {t.get("name") for t in all_tools}
            allowed_tools = [t for t in allowed_tools if t in registered_names]
            fallback_tools = [t for t in fallback_tools if t in registered_names]

            normalized = {
                "id": step_id,
                "step": step_name,
                "step_type": step_type,
                "allowed_tools": allowed_tools,
                "fallback_tools": fallback_tools,
                "expected_output": expected_output,
                "required": required,
                "agent_type": item.get("agent_type", "executor"),
                "depends_on": item.get("depends_on", []),
            }
            steps.append(normalized)

        if not steps:
            logger.warning("Planner produced no valid steps, falling back to single-step plan")
            steps = [{"id": "step_1", "step": "Process the request", "step_type": "general", "allowed_tools": [], "fallback_tools": [], "expected_output": "result", "required": False, "agent_type": "executor", "depends_on": []}]

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
            # Auto-mark as required if any downstream step depends on it
            for other in steps:
                if step["id"] in other.get("depends_on", []):
                    step["required"] = True

        return steps
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        query = input_data.input_data.get("query", "")
        tools = input_data.input_data.get("tools", [])
        tools_summary = ""
        if tools:
            tool_names = [t.get("name", "unknown") for t in tools]
            tools_summary = ", ".join(tool_names)
        else:
            tools_summary = "none"

        os_info = f"{platform.system()} {platform.release()}"
        home_path = os.path.expanduser("~")
        desktop_path = _get_desktop_path()

        logger.info(f"Planner executing for query: {query}")

        # ALWAYS use LLM for planning. Rule-based decomposition is disabled.
        messages = [
            {"role": "system", "content": PLANNER_PROMPT.format(
                query=query,
                tools=tools_summary,
                os_info=os_info,
                home_path=home_path,
                desktop_path=desktop_path,
            )}
        ]

        try:
            result = await get_llm_client().complete_json(messages)
            steps = self._normalize_plan_response(result, home_path=home_path, desktop_path=desktop_path)
            
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
