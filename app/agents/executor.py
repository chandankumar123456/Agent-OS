import json
import os
import platform
from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any, Optional
from .llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.parser import ToolCallParser
from ..tools.registry import tool_registry
from ..tools.grounding import ToolGroundingLayer
from ..environments.desktop_env import DesktopSessionManager
from ..environments.execution_stabilizer import ActionStabilizer
from ..environments.window_registry import WindowRegistry
# Lazy import to avoid circular import with app.desktop.goal_loop
# DesktopGoalLoop = None  # type: ignore
from ..utils.paths import get_desktop_path as _get_desktop_path
from ..utils.paths import remap_tool_params as _remap_tool_params


EXECUTOR_PROMPT = """You are an Executor agent for Agent-OS. Your role is to EXECUTE specific steps from a plan using available tools.

ALLOWED TOOLS (you MUST select from this list ONLY):
{tools}

Step: {step}
Context: {context}

Operating System: {os_info}
User Desktop Path: {desktop_path}

ABSOLUTE RULES — FOLLOW WITHOUT EXCEPTION:
1. You MUST select a tool from the ALLOWED TOOLS list above ONLY. NEVER use a tool outside this list.
2. If the step involves creating, writing, reading, or modifying a file, you MUST call the filesystem tool (e.g., filesystem__write_file, filesystem__read_file) with concrete parameters.
3. If the step involves running a command or script, you MUST call the shell tool (e.g., shell__execute_command) with the exact command.
4. If the step involves web browsing or scraping, you MUST call the browser tool.
5. If the step involves calculation, you MUST call the calculator tool.
6. NEVER just describe what you would do — actually invoke the tool.
7. NEVER ask the user to run commands manually — use the shell tool.
8. ALWAYS use ABSOLUTE file paths. NEVER use relative paths like ./file.py.
9. On Windows, use backslashes in paths (e.g., C:\\Users\\Name\\Desktop\\file.txt). On macOS/Linux, use forward slashes.

DESKTOP GUI AUTOMATION — STRICT WORKFLOW:
10. If the step involves interacting with a desktop GUI:
    a. You MUST call desktop__get_ui_tree first to understand the screen state and obtain element IDs.
    b. Locate the ID of the target element in the returned tree.
    c. Call desktop__click_element(id) or desktop__type_element(id, text).
    d. NEVER guess x/y coordinates manually. NEVER call desktop__click(x, y).
    e. If an element appears unclickable, you may use desktop__focus_and_interact(id, key) as a fallback.

SHELL SHORTCUT PROHIBITION:
11. You MUST NEVER use shell__execute_command to open, launch, or interact with GUI applications (e.g., Notepad, Calculator, Chrome, VS Code) if the task requires further interaction within that app (typing, clicking, navigating).
    a. Opening a GUI app via PowerShell/batch and then trying to interact with it will FAIL because the shell tool cannot see or control the UI.
    b. Desktop apps MUST use desktop__get_ui_tree -> desktop__click_element / desktop__type_element.
    c. Browser apps MUST use browser_env__launch -> browser_env__navigate / browser_env__type / browser_env__click.
    d. The ONLY exception: if the task is purely to launch an app with no follow-up interaction, shell__execute_command is acceptable.

If you need to use a tool, return JSON with a tool_call:
{{"tool_call": {{"name": "tool_name", "params": {{"param1": "value1"}}}}}}

If no tool is needed, return:
{{"result": "what you found or produced", "details": "additional information"}}"""


class ExecutorAgent:
    name: str = "executor"
    role: AgentRole = AgentRole.EXECUTOR
    MAX_TOOL_ROUNDS: int = 5
    allowed_tools: Optional[List[str]] = None

    def _get_allowed_tools(self, input_data: AgentInput) -> Optional[List[str]]:
        """Determine allowed tools from agent config or input. None means allow all."""
        if input_data.allowed_tools is not None:
            return input_data.allowed_tools
        return self.allowed_tools

    def _get_fallback_tools(self, input_data: AgentInput) -> Optional[List[str]]:
        """Determine fallback tools from agent config or input."""
        if input_data.fallback_tools is not None:
            return input_data.fallback_tools
        return None

    def _filter_tools(self, tools_schema: List[Dict[str, Any]], allowed: Optional[List[str]]) -> List[Dict[str, Any]]:
        if allowed is None:
            return tools_schema
        allowed_set = set(allowed)
        return [t for t in tools_schema if t.get("name") in allowed_set]

    def _is_desktop_task(self, input_data: AgentInput) -> bool:
        """Check if this is a desktop automation task.

        Detects desktop tasks by checking for explicit env_type, desktop tools in the tool
        list, or a desktop_automation step_type. This gates whether the executor delegates
        to the goal-driven desktop loop with DesktopSession, ActionStabilizer, and WindowRegistry.
        """
        step_data = input_data.input_data
        if step_data.get("env_type", "").lower() == "desktop":
            return True
        tools = step_data.get("tools", [])
        if any(t.get("name", "").startswith(("desktop_env__", "desktop__")) for t in tools):
            return True
        if step_data.get("step_type", "").lower() == "desktop_automation":
            return True
        return False

    async def _execute_desktop_goal(
        self, input_data: AgentInput, session: Any = None
    ) -> AgentOutput:
        """Execute a desktop automation step using the goal-driven loop.

        Reuses DesktopSession (with ActionStabilizer + WindowRegistry attached) and
        DesktopGoalLoop for observe → act → verify cycles. This is the legacy executor's
        desktop path, sharing the same components as the LangGraph executor_node.

        Args:
            input_data: The agent input with step, context, tools, etc.
            session: Optional pre-created DesktopSession. If None, creates one via
                     DesktopSessionManager (for standalone usage outside execute()).
        """
        task_id_str = str(input_data.task_id)
        step = input_data.input_data.get("step", "")
        context = input_data.context

        # Ground tools for desktop automation
        grounding = ToolGroundingLayer()
        tools_schema = input_data.input_data.get("tools", [])
        grounded_tools = grounding.filter_tools_for_step(step, tools_schema)
        grounded_tool_names = {t["name"] for t in grounded_tools}
        logger.debug(
            f"ExecutorAgent: grounded {len(grounded_tool_names)} tools for desktop step"
        )

        # Delegate to DesktopGoalLoop
        from ..desktop.goal_loop import DesktopGoalLoop
        goal_loop = DesktopGoalLoop(task_id=task_id_str)
        result = await goal_loop.execute(
            query=context.get("query", step),
            description=step,
            tool_registry=tool_registry,
            grounded_tools=grounded_tools,
            grounded_tool_names=grounded_tool_names,
        )

        if result.success:
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.SUCCESS,
                output_data={
                    "result": result.final_state.get("answer", ""),
                    "iterations": result.iterations,
                    "actions_performed": result.actions_performed,
                },
            )
        else:
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="desktop_goal_not_reached",
                error_message=result.error or "Desktop goal not reached",
                recoverable=True,
            )

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        step = input_data.input_data.get("step", "")
        context = input_data.context
        tools_schema = input_data.input_data.get("tools", [])
        allowed = self._get_allowed_tools(input_data)
        visible_tools = self._filter_tools(tools_schema, allowed)

        # Desktop task → use goal-driven loop with DesktopSession/ActionStabilizer/WindowRegistry
        if self._is_desktop_task(input_data):
            # Get or create desktop session (auto-inits ActionStabilizer + WindowRegistry)
            manager = DesktopSessionManager()
            session = await manager.get_or_create_session(str(input_data.task_id))
            logger.info(
                f"ExecutorAgent: created desktop session for task {input_data.task_id}"
            )
            return await self._execute_desktop_goal(input_data)

        # Fail fast if step requires filesystem but no filesystem tool is registered in this worker
        registered_tools = tool_registry.list_tools()
        has_filesystem_tool = any("filesystem" in t.get("name", "") for t in registered_tools)
        step_lower = step.lower()
        if any(k in step_lower for k in ("file", "write", "create", "read", "desktop", "directory", "folder")) and not has_filesystem_tool:
            logger.error(f"Step requires filesystem tool but none registered in worker: {step}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="tool_unavailable",
                error_message="Filesystem tools are not registered in this worker. Required for step: " + step,
                recoverable=False,
            )

        os_info = f"{platform.system()} {platform.release()}"
        desktop_path = _get_desktop_path()

        # Use custom prompt if configured, otherwise default
        custom_prompt = getattr(self, "_custom_prompt", None)
        if custom_prompt:
            system_prompt = custom_prompt.format(
                step=step,
                context=context,
                tools=json.dumps(visible_tools, indent=2) if visible_tools else "No tools available",
                os_info=os_info,
                desktop_path=desktop_path,
            )
        else:
            system_prompt = EXECUTOR_PROMPT.format(
                step=step,
                context=context,
                tools=json.dumps(visible_tools, indent=2) if visible_tools else "No tools available",
                os_info=os_info,
                desktop_path=desktop_path,
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Execute this step: {step}"}
        ]

        try:
            final_result = None
            for round_num in range(self.MAX_TOOL_ROUNDS):
                result = await get_llm_client().complete_json(messages)
                final_result = result

                # Check for tool call
                tool_call = ToolCallParser.parse(result)
                if not tool_call:
                    break

                tool_name = tool_call["name"]
                tool_params = tool_call["params"]

                # Enforce tool access control
                if allowed is not None and tool_name not in allowed:
                    logger.warning(f"Tool access denied: '{tool_name}' not in allowed tools {allowed}")
                    error_msg = f"Tool '{tool_name}' is not authorized for this agent."
                    messages.append({"role": "assistant", "content": json.dumps(result)})
                    messages.append({
                        "role": "system",
                        "content": f"Error: {error_msg} Please use only allowed tools."
                    })
                    continue

                logger.info(f"Executor invoking tool: {tool_name} with params: {tool_params}")

                # Remap any hallucinated foreign paths in tool parameters
                home_path = os.path.expanduser("~")
                desktop_path = _get_desktop_path()
                tool_params = _remap_tool_params(tool_params, home_path, desktop_path)

                # Execute tool
                tool_output = await tool_registry.execute(tool_name, tool_params)

                if tool_output.success:
                    tool_result = tool_output.result
                else:
                    tool_result = {"error": tool_output.error}

                # Feed tool result back as assistant message
                messages.append({"role": "assistant", "content": json.dumps(result)})
                messages.append({
                    "role": "system",
                    "content": f"Tool '{tool_name}' returned: {json.dumps(tool_result)}. Continue with your analysis."
                })

                logger.info(f"Tool round {round_num + 1} completed for step: {step}")

            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.SUCCESS,
                output_data=final_result,
                confidence=0.85,
                reasoning_trace=[
                    f"Executed step: {step}",
                    f"Result: {final_result.get('result', 'completed') if final_result else 'completed'}"
                ]
            )
        except Exception as e:
            logger.error(f"Executor failed: {e}")
            return AgentOutput(
                task_id=input_data.task_id,
                step_id=input_data.step_id,
                status=AgentStatus.FAILURE,
                error_type="execution_error",
                error_message=str(e),
                recoverable=True
            )

