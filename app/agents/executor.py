import json
import os
import platform
import re
from .base import AgentInput, AgentOutput, AgentRole, AgentStatus
from uuid import uuid4
from typing import List, Dict, Any, Optional
from .llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.parser import ToolCallParser
from ..tools.registry import tool_registry


def _get_desktop_path() -> str:
    """Return the user's Desktop absolute path for the current OS."""
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        # Try user's personal Desktop first, fall back to Public Desktop
        user_desktop = os.path.join(home, "Desktop")
        if os.path.isdir(user_desktop):
            return user_desktop
        public_desktop = os.path.join(os.path.dirname(home), "Public", "Desktop")
        if os.path.isdir(public_desktop):
            return public_desktop
        return os.path.join(home, "Desktop")
    elif platform.system() == "Darwin":
        return os.path.join(home, "Desktop")
    else:
        return os.path.join(home, "Desktop")


def _looks_like_foreign_path(path: str) -> bool:
    """Check if a path looks like it belongs to a different OS."""
    if not path or not isinstance(path, str):
        return False
    system = platform.system()
    # Unix-style absolute path on Windows
    if system == "Windows" and (path.startswith("/") or path.startswith("~")):
        return True
    # Windows-style absolute path on Unix
    if system in ("Linux", "Darwin") and len(path) > 1 and path[1] == ":":
        return True
    return False


def _remap_path(path: str, home_path: str, desktop_path: str) -> str:
    """Remap a hallucinated foreign path to the current OS."""
    if not _looks_like_foreign_path(path):
        return path

    system = platform.system()

    # Expand ~ to home first
    if path.startswith("~/"):
        path = os.path.join(home_path, path[2:])
        return os.path.normpath(path)

    if system == "Windows":
        # Handle /home/$USER/Desktop/... or /home/name/Desktop/...
        if re.match(r"/home/[^/]+/Desktop(/|$)", path):
            suffix = re.sub(r"/home/[^/]+/Desktop", "", path, count=1)
            return os.path.normpath(os.path.join(desktop_path, suffix.lstrip("/").replace("/", os.sep)))
        # Handle /home/$USER/... or /home/name/...
        if re.match(r"/home/[^/]+(/|$)", path):
            suffix = re.sub(r"/home/[^/]+", "", path, count=1)
            return os.path.normpath(os.path.join(home_path, suffix.lstrip("/").replace("/", os.sep)))
        # Generic Unix absolute path on Windows - map to home
        if path.startswith("/"):
            return os.path.normpath(os.path.join(home_path, path[1:].replace("/", os.sep)))

    if system in ("Linux", "Darwin"):
        # Handle C:\Users\Name\Desktop\... or similar
        if re.match(r"[A-Za-z]:\\Users\\[^\\]+\\Desktop(\\|$)", path):
            suffix = re.sub(r"[A-Za-z]:\\Users\\[^\\]+\\Desktop", "", path, count=1)
            return os.path.join(desktop_path, suffix.lstrip("\\").replace("\\", os.sep))
        # Handle C:\Users\Name\... or any drive letter path
        if len(path) > 1 and path[1] == ":":
            # Strip drive letter and leading backslashes, map under home
            suffix = re.sub(r"[A-Za-z]:(\\|/)", "", path, count=1)
            return os.path.join(home_path, suffix.replace("\\", os.sep))

    return path


def _normalize_paths_in_text(text: str, home_path: str, desktop_path: str) -> str:
    """Replace common hallucinated paths in a text block with actual OS paths."""
    if not text or not isinstance(text, str):
        return text

    # Find candidate absolute paths
    pattern = re.compile(r"(?:^|\s)([~]?(?:/[A-Za-z0-9_\-\$.]+)+/?|[A-Za-z]:\\(?:[^\\\s]+\\?)+)(?=$|\s)")

    def replace_match(m):
        path = m.group(1)
        remapped = _remap_path(path, home_path, desktop_path)
        return m.group(0).replace(path, remapped)

    return pattern.sub(replace_match, text)


def _remap_tool_params(params: Dict[str, Any], home_path: str, desktop_path: str) -> Dict[str, Any]:
    """Recursively remap foreign paths in tool parameters."""
    if not isinstance(params, dict):
        return params
    remapped = {}
    for key, value in params.items():
        if isinstance(value, str):
            remapped[key] = _remap_path(value, home_path, desktop_path)
        elif isinstance(value, dict):
            remapped[key] = _remap_tool_params(value, home_path, desktop_path)
        elif isinstance(value, list):
            remapped[key] = [
                _remap_path(v, home_path, desktop_path) if isinstance(v, str) else
                _remap_tool_params(v, home_path, desktop_path) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            remapped[key] = value
    return remapped


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

    async def execute(self, input_data: AgentInput) -> AgentOutput:
        step = input_data.input_data.get("step", "")
        context = input_data.context
        tools_schema = input_data.input_data.get("tools", [])
        allowed = self._get_allowed_tools(input_data)
        visible_tools = self._filter_tools(tools_schema, allowed)

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

