"""LangGraph node functions for AgentOS agent execution."""
import json
import os
import platform
import re
from typing import Dict, Any, List, Set, Optional
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt

from ..agents.llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.registry import tool_registry
from ..tools.grounding import tool_grounding_layer
from ..workflows.decomposer import workflow_decomposer
from ..capabilities import verification_engine, recovery_engine
from ..capabilities.models import VerificationResult, RecoveryAction
from ..observability import observability_bus, ObservabilityEventType
from ..safety.gate import SafetyGate, ActionSeverity
from ..orchestrator.event_bus import event_bus, Event
from ..guardrails.validator import guardrails
from .state import AgentState
from ..execution_state import ExecutionState, ToolExecutionRecord, ExecutionVerdict
from ..orchestrator.errors import ErrorType, ErrorCode

async def _validate_node_output(node_name: str, task_id: str, result: Dict[str, Any], output_content: Any) -> Dict[str, Any]:
    """Helper to validate node output through guardrails. Returns updated result if blocked."""
    from ..guardrails.validator import guardrails
    status = result.get("status", "unknown")
    payload = {"status": status, "node": node_name}
    
    # Add snippet of output for content-based guardrails
    if isinstance(output_content, str):
        payload["output"] = output_content[:1000]
    elif isinstance(output_content, (dict, list)):
        payload["output"] = str(output_content)[:1000]
        
    out_valid = await guardrails.verify_output(payload)
    if not out_valid:
        logger.warning(f"[{node_name}] Guardrail output validation failed for task {task_id}")
        result["error"] = f"{node_name.replace('_node', '').capitalize()} guardrail validation failed"
        result["status"] = "guardrail_blocked"
        if "verified" in result:
            result["verified"] = False
    return result

from ..desktop.goal_loop import DesktopGoalLoop


def _to_openai_messages(messages):
    """Map LangChain message types to OpenAI roles."""
    role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
    return [{"role": role_map.get(m.type, m.type), "content": m.content} for m in messages]


def _get_desktop_path() -> str:
    """Return the user's Desktop absolute path for the current OS."""
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        user_desktop = os.path.join(home, "Desktop")
        if os.path.isdir(user_desktop):
            return user_desktop
        public_desktop = os.path.join(os.path.dirname(home), "Public", "Desktop")
        if os.path.isdir(public_desktop):
            return public_desktop
        return user_desktop
    elif platform.system() == "Darwin":
        return os.path.join(home, "Desktop")
    else:
        return os.path.join(home, "Desktop")


def _extract_path_from_description(description: str) -> Optional[str]:
    """Extract a likely file path from a step description."""
    import re
    # Match Windows or Unix absolute paths
    matches = re.findall(r"([A-Za-z]:\\[^\s\"'<>]+|/~?(?:/[^\s\"'<>]+)+)", description)
    if matches:
        return matches[0]
    return None


def _build_default_params(tool_name: str, description: str) -> Optional[Dict[str, Any]]:
    """Build default parameters for obviously-intented tools without LLM."""
    path = _extract_path_from_description(description)
    if tool_name == "filesystem__read_file" and path:
        return {"path": path}
    if tool_name == "filesystem__write_file" and path:
        # For write, we can't guess content; return None to force LLM
        return None
    if tool_name == "filesystem__list_directory" and path:
        return {"path": path}
    if tool_name == "filesystem__search_files":
        path_match = re.findall(r"([A-Za-z]:\\[^\s\"'<>]*|/~?(?:/[^\s\"'<>]+)*)", description)
        search_path = path_match[0] if path_match else _get_desktop_path()
        words = description.lower().split()
        stopwords = {"find", "search", "locate", "look", "for", "my", "the", "a", "in", "under", "at", "file", "files", "and", "or"}
        pattern = "*"
        for w in words:
            if w not in stopwords and len(w) > 2:
                pattern = f"*{w}*"
                break
        return {"path": search_path, "pattern": pattern}
    if tool_name == "document__parse" and path:
        return {"path": path}
    if tool_name == "shell__execute_command":
        # Only auto-build for very obvious commands
        if "open" in description.lower() and "chrome" in description.lower() and path:
            return {"command": f'start chrome "{path}"'}
        if "open" in description.lower() and "explorer" in description.lower():
            open_path = path or os.path.expanduser("~")
            return {"command": f'explorer "{open_path}"'}
    if tool_name.startswith("browser_env__"):
        if "navigate" in description.lower() or "go to" in description.lower():
            url_match = re.findall(r"https?://[^\s\"'<>]+", description)
            if url_match:
                return {"url": url_match[0]}
        # Empty dict is NOT valid params for browser tools — force LLM generation
        return None
    if tool_name.startswith("desktop_env__"):
        # Empty dict is NOT valid params for desktop tools — force LLM generation
        return None
    return None


def _deterministic_tool_select(description: str, available_tools: List[Dict[str, Any]]) -> Optional[str]:
    """If a step description maps to exactly one obvious tool, return it without LLM."""
    grounded = tool_grounding_layer.filter_tools_for_step(description, available_tools)
    if len(grounded) == 1:
        name = grounded[0].get("name")
        # Only auto-select for very safe, obvious tools
        safe_tools = {
            "filesystem__read_file", "filesystem__list_directory", "filesystem__search_files",
            "document__parse", "shell__execute_command", "browser_env__navigate",
            "browser_env__screenshot", "desktop_env__screenshot", "desktop_env__get_window_list",
        }
        if name in safe_tools:
            return name
    return None


PLANNER_SYSTEM_PROMPT_TEMPLATE = """You are an expert planning agent. Given a user query, break it down into a clear, ordered list of steps.
Each step MUST specify:
- step_number: integer starting at 1
- description: what to do (be specific about file paths and tool names)
- step_type: exactly one of [file_search, file_read, file_write, document_processing, content_generation, browser_open, browser_navigation, desktop_automation, shell_execution, web_search, general]
- tool: primary tool name to use (or null if no tool needed)
- allowed_tools: list of exact tool names this step may use
- fallback_tools: list of exact fallback tool names if primary fails
- expected_output: what the step should produce
- required: boolean, true if downstream steps depend on this step succeeding
- depends_on: list of step_numbers this step depends on (empty for first step)

CRITICAL RULES:
- Each step MUST use tools from ONLY ONE execution environment.
- file_search / file_read / file_write / document_processing / content_generation steps: ONLY filesystem__* and shell__* tools.
- browser_open / browser_navigation steps: ONLY browser_env__* tools.
- desktop_automation steps: ONLY desktop_env__* tools.
- shell_execution steps: ONLY shell__* tools.
- web_search steps: ONLY cloud__* or web_search tools.
- NEVER mix browser, desktop, and filesystem tools in the same step.
- For local file tasks, prefer filesystem tools first. Use desktop tools ONLY as a fallback.
- NEVER use browser tools to search the local filesystem.
- Chrome should only be used at the final display step, not for file discovery.

When the task involves files:
- Use exact absolute paths, never relative paths.
- On Windows use backslashes (e.g., C:\\Users\\Name\\Desktop\\file.txt).
- On Linux/macOS use forward slashes (e.g., /home/name/Desktop/file.txt).

Current operating system: {os_info}
User home directory: {home_path}
User Desktop path: {desktop_path}

When the task involves creating/writing files, always use the filesystem__write_file tool.
When the task involves running commands, always use the shell__execute_command tool.

Respond ONLY with valid JSON in this format:
{{"plan": [{{"step_number": 1, "description": "...", "step_type": "...", "tool": "...", "allowed_tools": ["..."], "fallback_tools": ["..."], "expected_output": "...", "required": true/false, "depends_on": []}}]}}

Execution Environment Awareness:
- If the user asks to "open chrome", "open browser", "search in browser", "login to", "click", "fill form", or "navigate website", use browser_env__* tools (e.g., browser_env__launch, browser_env__search).
- If the user asks for general information retrieval ("search latest AI news", "find research papers", "summarize topic"), use cloud__search_web or cloud__http_request.
- Do NOT use cloud__search_web when the user explicitly wants browser UI interaction.
"""


VERIFIER_SYSTEM_PROMPT = """You are a verification agent. Given a user query, the execution plan, and the results, verify if the task was completed successfully.

Respond ONLY with valid JSON:
{"verified": true/false, "notes": "explanation of verification result"}
"""


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Generate an execution plan from the user query, informed by capability assessment.

    Uses deterministic workflow decomposition first for complex multi-step tasks.
    Falls back to LLM planner for simple or ambiguous queries.
    """
    query = state.get("query", "")
    task_id = state.get("task_id", "")
    logger.info(f"[planner_node] Planning for task {task_id}")

    os_info = f"{platform.system()} {platform.release()}"
    home_path = os.path.expanduser("~")
    desktop_path = _get_desktop_path()

    # ── Deterministic Workflow Decomposition ──────────────────────────
    phases = workflow_decomposer.decompose(query)
    if phases:
        logger.info(f"[planner_node] Using deterministic decomposition: {len(phases)} phases")
        plan = []
        for i, phase in enumerate(phases):
            # Strict tool grounding using phase.intent (NOT description keyword matching)
            all_tools = tool_registry.list_tools()
            primary_tools = tool_grounding_layer.get_primary_tools(phase.intent, all_tools, exclude_desktop_for_non_desktop=True)
            fallback_tools = tool_grounding_layer.get_fallback_tools(phase.intent, all_tools)

            allowed_tool_names = [t["name"] for t in primary_tools[:8]]
            fallback_tool_names = [t["name"] for t in fallback_tools[:4]]
            suggested_tool = allowed_tool_names[0] if allowed_tool_names else (fallback_tool_names[0] if fallback_tool_names else None)

            tool_hint = ""
            if allowed_tool_names:
                tool_hint = f"Use one of: {', '.join(allowed_tool_names[:5])}."

            # Extract paths from query for this phase
            paths = workflow_decomposer.extract_paths(query)
            path_hint = ""
            if paths and phase.name in ("file_search", "file_read", "document_processing", "content_generation"):
                path_hint = f" Paths mentioned: {', '.join(paths[:2])}."

            # Preserve decomposer-specific atomic descriptions to avoid vague desktop steps.
            desc = phase.description.strip() if phase.description else phase.name
            if "original task:" not in desc.lower():
                desc = f"{desc} Original task: {query}"

            # Sequential dependency gate: every non-final step is required for downstream work.
            required = i < (len(phases) - 1)

            plan.append({
                "step_number": i + 1,
                "description": f"{desc}.{path_hint} {tool_hint}",
                "step_type": phase.name,
                "tool": suggested_tool,
                "allowed_tools": allowed_tool_names,
                "fallback_tools": fallback_tool_names,
                "depends_on": [i] if i > 0 else [],
                "expected_output": f"Completed {phase.name} for: {query}",
                "required": required,
            })

        await observability_bus.emit_safe(
            ObservabilityEventType.PLANNER_REASONING,
            task_id=task_id,
            trace_id=state.get("trace_id"),
            payload={"plan": plan, "capability_context": f"deterministic_decomposition:{[p.name for p in phases]}"},
            source="planner_node",
        )
        return {
            "plan": plan,
            "current_step_index": 0,
            "messages": [AIMessage(content=f"Deterministic plan: {json.dumps(plan, indent=2)}")],
            "status": "planning_complete",
        }

    # ── Fallback to LLM planner for simple/ambiguous tasks ────────────
    cap_assessment = state.get("capability_assessment")
    capability_context = ""
    if cap_assessment:
        primary = cap_assessment.get("primary_capability", "unknown")
        caps = [c["capability"] for c in cap_assessment.get("required_capabilities", [])]
        safety = cap_assessment.get("safety_flags", [])
        capability_context = (
            f"\nDetected capabilities: {', '.join(caps)}\n"
            f"Primary capability: {primary}\n"
        )
        if safety:
            capability_context += f"Safety flags: {', '.join(safety)}\n"

    system_prompt = PLANNER_SYSTEM_PROMPT_TEMPLATE.format(
        os_info=os_info,
        home_path=home_path,
        desktop_path=desktop_path,
    ) + capability_context

    llm = get_llm_client()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"User query: {query}"),
    ]

    try:
        raw = await llm.complete_json(
            messages=_to_openai_messages(messages),
            response_schema={
                "type": "object",
                "properties": {
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number": {"type": "integer"},
                                "description": {"type": "string"},
                                "step_type": {"type": "string"},
                                "tool": {"type": ["string", "null"]},
                                "allowed_tools": {"type": "array", "items": {"type": "string"}},
                                "fallback_tools": {"type": "array", "items": {"type": "string"}},
                                "expected_output": {"type": "string"},
                            },
                            "required": ["step_number", "description", "tool", "expected_output"],
                        },
                    }
                },
                "required": ["plan"],
            },
        )
        plan = raw.get("plan", [])
        if not plan:
            plan = [{"step_number": 1, "description": query, "tool": None, "expected_output": "Answer the user's query"}]
    except Exception as e:
        logger.error(f"[planner_node] Planning failed: {e}")
        plan = [{"step_number": 1, "description": query, "tool": None, "expected_output": "Answer the user's query"}]

    # ── Post-process LLM plan: ensure tool constraints are always present ──
    available_tools = tool_registry.list_tools()
    for step in plan:
        desc = step.get("description", "")
        # Ensure step_type is set
        if not step.get("step_type"):
            step["step_type"] = tool_grounding_layer.classify_intent(desc)
        step_type = step.get("step_type", "")
        # Ensure allowed_tools are grounded if missing
        if not step.get("allowed_tools"):
            primary = tool_grounding_layer.get_primary_tools(step_type, available_tools, exclude_desktop_for_non_desktop=True)
            step["allowed_tools"] = [t["name"] for t in primary[:8]]
        # Ensure fallback_tools are grounded if missing
        if not step.get("fallback_tools"):
            fallback = tool_grounding_layer.get_fallback_tools(step_type, available_tools)
            step["fallback_tools"] = [t["name"] for t in fallback[:4]]

    await observability_bus.emit_safe(
        ObservabilityEventType.PLANNER_REASONING,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        payload={"plan": plan, "capability_context": capability_context},
        source="planner_node",
    )

    # ── Output Validation at Node Exit ────────────────────────────────
    result = {
        "plan": plan,
        "current_step_index": 0,
        "messages": [AIMessage(content=f"Plan: {json.dumps(plan, indent=2)}")],
        "status": "planning_complete",
    }
    return await _validate_node_output("planner_node", task_id, result, plan)


async def executor_node(state: AgentState) -> Dict[str, Any]:
    """Execute the current step using grounded tool selection.

    Flow:
    1. Ground tools to step intent (filter allowed tools)
    2. Try deterministic tool selection (skip LLM for obvious cases)
    3. If ambiguous, use LLM with ONLY grounded tools
    4. Reject LLM tool choices outside grounded set
    5. If tool missing, try dynamic build
    """
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    task_id = state.get("task_id", "")

    if idx >= len(plan):
        logger.info(f"[executor_node] All steps complete for task {task_id}")
        result = {"status": "execution_complete"}
        return await _validate_node_output("executor_node", task_id, result, "All steps executed")

    step = plan[idx]
    step_number = step.get("step_number", idx + 1)
    description = step.get("description", "")
    suggested_tool = step.get("tool")

    logger.info(f"[executor_node] Executing step {step_number} for task {task_id}: {description}")

    # Initialize canonical execution state
    exec_state_data = state.get("execution_state")
    execution_state = ExecutionState.from_dict(exec_state_data) if exec_state_data else ExecutionState(task_id=task_id)
    execution_state.current_step = step_number

    await observability_bus.emit_safe(
        ObservabilityEventType.STEP_STARTED,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        step_id=str(step_number),
        payload={"description": description, "suggested_tool": suggested_tool},
        source="executor_node",
    )

    # ── Dependency Gate ───────────────────────────────────────────────
    prior_steps = state.get("steps", [])[:idx]
    for prior in prior_steps:
        if prior.get("required", False):
            tool_results = prior.get("tool_results", [])
            if not any(r.get("success") for r in tool_results):
                error_msg = (
                    f"Required step {prior['step_number']} ({prior.get('description', '')[:60]}) failed. "
                    f"Cannot proceed to step {step_number}."
                )
                logger.error(f"[executor_node] {error_msg}")
                # Halt the workflow entirely — do not advance to subsequent steps
                result = {
                    "steps": state.get("steps", []),
                    "current_step_index": len(plan),  # Skip to end so graph terminates
                    "error": error_msg,
                    "tool_calls": state.get("tool_calls", []),
                    "messages": [AIMessage(content=f"Workflow halted: {error_msg}")],
                    "status": "failed",
                }
                return await _validate_node_output("executor_node", task_id, result, error_msg)

    # ── Tool Selection: Use Planner Constraints (NO re-grounding) ─────
    available_tools = tool_registry.list_tools()
    available_tool_map = {t["name"]: t for t in available_tools}

    # Primary: planner's allowed_tools
    explicit_allowed = step.get("allowed_tools", [])
    explicit_fallback = step.get("fallback_tools", [])

    grounded_tools = []
    if explicit_allowed:
        grounded_tools = [available_tool_map[name] for name in explicit_allowed if name in available_tool_map]
    if not grounded_tools and explicit_fallback:
        grounded_tools = [available_tool_map[name] for name in explicit_fallback if name in available_tool_map]
    if not grounded_tools:
        # Legacy fallback: only if planner didn't specify constraints
        step_type = step.get("step_type", "").lower()
        # For ANY specialized intent, do NOT re-ground from description alone;
        # the description may not contain the right keywords and will fall back to generic tools.
        # Only "general" steps may use the description-based re-grounding.
        if step_type and step_type != "general":
            logger.warning(
                f"[executor_node] Step {step_number} (type={step_type}) has no grounded tools and no planner constraints. "
                f"Returning empty tool set to fail loudly."
            )
            grounded_tools = []
        else:
            grounded_tools = tool_grounding_layer.filter_tools_for_step(description, available_tools)

    grounded_tool_names = {t["name"] for t in grounded_tools}
    logger.info(f"[executor_node] Grounded tools for step {step_number}: {grounded_tool_names}")

    # Diagnostic: log what was rejected
    rejected = [t["name"] for t in available_tools if t["name"] not in grounded_tool_names]
    logger.info(f"[executor_node] Rejected tools for step {step_number}: {rejected[:20]}")

    # ── Desktop Goal-Driven Execution Loop ─────────────────────────────
    is_desktop_step = bool(
        any(t.get("name", "").startswith(("desktop_env__", "desktop__")) for t in grounded_tools)
        or step.get("step_type", "").lower() == "desktop_automation"
    )
    if is_desktop_step:
        logger.info(f"[executor_node] Desktop step detected for task {task_id}. Running goal-driven loop via DesktopGoalLoop.")
        goal_loop = DesktopGoalLoop(task_id=task_id)
        goal_loop.max_iterations = state.get("max_tool_rounds", 5)
        desktop_result = await goal_loop.execute(
            query=state.get("query", ""),
            description=description,
            tool_registry=tool_registry,
            grounded_tools=grounded_tools,
            grounded_tool_names=grounded_tool_names,
            max_iterations=state.get("max_tool_rounds", 5),
        )
        # Map DesktopGoalResult (or mock dict) to state dict
        if hasattr(desktop_result, 'actions_performed'):
            # Real DesktopGoalResult dataclass
            status = "step_executed" if desktop_result.success else "incomplete"
            actions = desktop_result.actions_performed
            iterations = desktop_result.iterations
            answer = desktop_result.final_state.get("answer", "") if desktop_result.final_state else ""
        else:
            # Support dict return for test mocking
            status = desktop_result.get("status", "success")
            actions = desktop_result.get("actions", [])
            iterations = desktop_result.get("iterations", 0)
            answer = desktop_result.get("answer", "")

        # Record desktop loop results in canonical execution state
        for action in actions:
            if isinstance(action, dict):
                tool_name = action.get("tool", "unknown")
                result_dict = action.get("result", {})
                tool_record = ToolExecutionRecord.from_tool_result(tool_name, result_dict)
                execution_state.record_tool(step_number, description, tool_record)

        steps = list(state.get("steps", []))
        steps.append({
            "step_number": step_number,
            "description": description,
            "output": answer,
            "tool_results": [
                a.get("result", {}) if isinstance(a, dict) else {}
                for a in actions
            ],
        })

        return {
            "steps": steps,
            "current_step_index": idx + 1,
            "tool_calls": actions,
            "messages": [AIMessage(content=f"Step {step_number} result: {answer}")],
            "verification_reports": state.get("verification_reports", []),
            "recovery_decisions": state.get("recovery_decisions", []),
            "status": status,
            "desktop_iterations": iterations,
            "execution_state": execution_state.to_dict(),
        }

    # ── Deterministic Execution (skip LLM for obvious cases) ──────────
    # Try planner's suggested tool first
    det_tool = None
    if suggested_tool and suggested_tool in grounded_tool_names:
        det_tool = suggested_tool
    else:
        # Obey planner constraints: pick the first grounded tool instead of re-grounding
        if grounded_tools:
            det_tool = grounded_tools[0].get("name")

    if det_tool and det_tool in grounded_tool_names:
        default_params = _build_default_params(det_tool, description)
        if default_params is not None:
            logger.info(f"[executor_node] Deterministic execution: {det_tool}")
            tool_params = default_params.copy()
            return await _execute_tool_call(
                task_id=task_id,
                step_number=step_number,
                description=description,
                tool_name=det_tool,
                tool_params=tool_params,
                state=state,
                idx=idx,
                grounded_tool_names=grounded_tool_names,
            )

    # ── LLM-Driven Parameter Generation Only ──────────────────────────
    tools_json = json.dumps(grounded_tools, indent=2, default=str)

    os_info = f"{platform.system()} {platform.release()}"
    home = os.path.expanduser("~")
    desktop_path = os.path.join(home, "Desktop")

    # Build execution context from prior steps
    prior_context = ""
    if prior_steps:
        prior_context_lines = []
        for s in prior_steps:
            prior_context_lines.append(
                f"Step {s['step_number']}: {s['description']}\n"
                f"Output: {s.get('output', '')[:500]}"
            )
        prior_context = "\n\nPreviously completed steps:\n" + "\n---\n".join(prior_context_lines)

    # Browser state hint
    browser_hint = ""
    if any(t.get("name", "").startswith("browser_env__") for t in grounded_tools):
        browser_hint = (
            "\nIMPORTANT: If a browser_env tool has already been used in a previous step, "
            "do NOT launch or navigate again unless explicitly required. Reuse the existing session."
        )

    # Suggested tool hint
    suggested_hint = ""
    if suggested_tool and suggested_tool in grounded_tool_names:
        suggested_hint = f"\nUse this tool if it fits the step: {suggested_tool}"

    original_query = state.get("query", "")

    system_prompt = f"""You are an execution agent. Your job is to CARRY OUT the given step by any means necessary.
You have access to the following GROUNDED tools. You MUST select a tool from this list ONLY.

Original user query: {original_query}

Allowed tools for this step:
{tools_json}

Current operating system: {os_info}
User home directory: {home}
User Desktop path: {desktop_path}{prior_context}{browser_hint}{suggested_hint}

CRITICAL RULES:
1. You MUST select a tool from the ALLOWED TOOLS list above. NEVER use a tool not in the list.
2. If the step asks you to create, write, read, or modify a file, use a filesystem tool.
3. If the step asks you to run a command or script, use the shell tool.
4. If the step asks you to browse or scrape the web, use the browser tool.
5. Do NOT just describe what you would do — actually invoke the tool with concrete parameters.
6. Use exact parameter names from the tool schema.
7. ALWAYS use ABSOLUTE file paths. NEVER use relative paths.
8. When creating files on Windows, use backslashes. On Linux/macOS, use forward slashes.
9. NEVER repeat a tool call that was already successfully executed in a previous step unless the user explicitly asks you to do it again.
10. If NO tool is needed, provide a direct answer.

Respond with JSON in one of these formats:

To call a tool:
{{"tool_call": {{"name": "tool_name", "params": {{"param1": "value1"}}}}}}

To provide a direct answer (only if no tool is needed):
{{"answer": "your response", "details": "additional info"}}
"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Step to execute: {description}"),
    ]

    MAX_ROUNDS = state.get("max_tool_rounds", 5)
    calls_this_step: set = set()
    tool_calls = list(state.get("tool_calls", []))
    step_tool_results = []
    final_answer = ""
    verification_reports = list(state.get("verification_reports", []))
    recovery_decisions = list(state.get("recovery_decisions", []))

    for round_num in range(MAX_ROUNDS):
        try:
            response = await get_llm_client().complete_json(
                messages=_to_openai_messages(messages)
            )
        except Exception as e:
            logger.error(f"[executor_node] LLM execution failed: {e}")
            final_answer = f"Error during execution: {e}"
            break

        tool_call_data = response.get("tool_call")
        if tool_call_data and isinstance(tool_call_data, dict):
            tool_name = tool_call_data.get("name")
            tool_params = tool_call_data.get("params", {})

            if not tool_name:
                final_answer = response.get("answer") or response.get("details") or json.dumps(response)
                break

            # ── Grounding Guard: reject tools outside allowed set ──────
            if tool_name not in grounded_tool_names:
                logger.warning(
                    f"[executor_node] LLM selected '{tool_name}' which is NOT in grounded set {grounded_tool_names}. "
                    f"Rejecting and forcing retry."
                )
                warn_msg = (
                    f"ERROR: '{tool_name}' is NOT allowed for this step. "
                    f"You MUST select from: {', '.join(sorted(grounded_tool_names))}. "
                    f"Try again with an allowed tool."
                )
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(content=warn_msg))
                continue

            # Inject task_id for observability and session management
            tool_params["_task_id"] = task_id

            # Duplicate-call guard
            call_signature = json.dumps({"name": tool_name, "params": tool_params}, sort_keys=True, default=str)
            if call_signature in calls_this_step:
                warn_msg = (
                    f"You already called '{tool_name}' with the same parameters in this step. "
                    "Do NOT repeat it. Either proceed with the next action or provide a direct answer."
                )
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(content=warn_msg))
                continue
            calls_this_step.add(call_signature)

            # Validate tool exists
            tool = tool_registry.get(tool_name)
            if not tool:
                error_msg = f"Tool '{tool_name}' not found"
                logger.error(f"[executor_node] {error_msg}")
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(content=f"Error: {error_msg}. Use a valid tool or provide a direct answer."))
                continue

            severity = SafetyGate().check_tool_call(tool_name, tool_params, state.get("query", ""))
            if severity == ActionSeverity.IRREVERSIBLE:
                await observability_bus.emit_safe(
                    ObservabilityEventType.SAFETY_CHECK,
                    task_id=task_id,
                    trace_id=state.get("trace_id"),
                    payload={"tool": tool_name, "severity": "irreversible", "params": tool_params},
                    source="safety_gate",
                )
                # Block irreversible actions pending human approval
                tool_result = {
                    "success": False,
                    "data": None,
                    "error": f"Action blocked: '{tool_name}' is classified as irreversible. Human approval required.",
                }
                tool_calls.append({
                    "step": step_number,
                    "tool": tool_name,
                    "result": tool_result,
                })
                step_tool_results.append(tool_result)
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(
                    content=f"Tool '{tool_name}' was BLOCKED as irreversible. You need explicit human approval to proceed."
                ))
                continue

            logger.info(f"[executor_node][TRACE] EXECUTING TOOL: tool_name='{tool_name}'")
            logger.info(f"[executor_node][TRACE] TOOL PAYLOAD: {json.dumps(tool_params, indent=2, default=str)}")
            await observability_bus.emit_safe(
                ObservabilityEventType.TOOL_INVOKED,
                task_id=task_id,
                trace_id=state.get("trace_id"),
                step_id=str(step_number),
                payload={"tool": tool_name, "params": tool_params},
                source="executor_node",
            )

            # Emit progress heartbeat so frontend stays alive during long operations
            try:
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.progress", {"task_id": task_id, "step": step_number, "tool": tool_name, "status": "executing"}, source="executor"),
                )
            except Exception:
                pass

            try:
                tool_output = await tool_registry.execute(tool_name, tool_params)
                logger.info(f"[executor_node][TRACE] RAW TOOL RESPONSE: success={tool_output.success} result={tool_output.result} error={tool_output.error}")
                tool_result = {
                    "success": tool_output.success,
                    "data": tool_output.result if tool_output.result is not None else str(tool_output),
                    "error": tool_output.error,
                }
            except Exception as e:
                logger.error(f"[executor_node][TRACE] Tool execution EXCEPTION: {e}")
                logger.error(f"[executor_node] Tool execution error: {e}")
                tool_result = {"success": False, "error": str(e)}

            # Record tool result
            tool_calls.append({
                "step": step_number,
                "tool": tool_name,
                "result": tool_result,
            })
            step_tool_results.append(tool_result)

            # Record in canonical execution state
            tool_record = ToolExecutionRecord.from_tool_result(tool_name, tool_result)
            execution_state.record_tool(step_number, description, tool_record)

            # ── Deterministic Verification ─────────────────────────────
            if tool_result["success"]:
                if "filesystem" in tool_name and tool_params.get("path"):
                    v_report = await verification_engine.verify(
                        task_id, None, "file_exists",
                        {"path": tool_params["path"]},
                    )
                    verification_reports.append(v_report.model_dump())
                    if v_report.result == VerificationResult.FAIL:
                        decision = await recovery_engine.decide(
                            task_id, None,
                            error=v_report.failure_reason,
                            verification_report=v_report,
                            current_tool=tool_name,
                            execution_state=execution_state.to_dict(),
                        )
                        recovery_decisions.append(decision.model_dump())
                        await observability_bus.emit_safe(
                            ObservabilityEventType.RECOVERY_ACTION,
                            task_id=task_id,
                            trace_id=state.get("trace_id"),
                            step_id=str(step_number),
                            payload={
                                "action": decision.action.value,
                                "reason": decision.reason,
                                "next_tool": decision.next_tool,
                            },
                            source="executor_node",
                        )
                        if decision.action == RecoveryAction.SWITCH_TOOL and decision.next_tool:
                            messages.append(HumanMessage(
                                content=f"Verification failed. Switching to alternative tool: {decision.next_tool}"
                            ))
                            continue
                        elif decision.action == RecoveryAction.RETRY:
                            messages.append(HumanMessage(
                                content=f"Verification failed. Retrying with same tool."
                            ))
                            continue

            messages.append(AIMessage(content=json.dumps(response)))
            messages.append(HumanMessage(
                content=f"Tool '{tool_name}' returned: {json.dumps(tool_result, indent=2)}. "
                        f"If the task is complete, provide a direct answer. If you need another tool, call it."
            ))
            continue
        else:
            final_answer = response.get("answer") or response.get("details") or json.dumps(response)
            break
    else:
        final_answer = f"Reached maximum tool rounds. Partial results: {json.dumps(step_tool_results, indent=2, default=str)}"

    if isinstance(final_answer, dict):
        final_answer = json.dumps(final_answer, indent=2, ensure_ascii=False)
    elif not isinstance(final_answer, str):
        final_answer = str(final_answer)

    step_output = {
        "step_number": step_number,
        "description": description,
        "output": final_answer,
        "tool_results": step_tool_results,
    }

    steps = list(state.get("steps", []))
    steps.append(step_output)

    await observability_bus.emit_safe(
        ObservabilityEventType.STEP_STARTED,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        step_id=str(step_number),
        payload={"status": "completed", "output_preview": final_answer[:200]},
        source="executor_node",
    )

    return {
        "steps": steps,
        "current_step_index": idx + 1,
        "tool_calls": tool_calls,
        "messages": [AIMessage(content=f"Step {step_number} result: {final_answer}")],
        "verification_reports": verification_reports,
        "recovery_decisions": recovery_decisions,
        "status": "step_executed",
        "execution_state": execution_state.to_dict(),
    }


async def _execute_tool_call(
    task_id: str,
    step_number: int,
    description: str,
    tool_name: str,
    tool_params: Dict[str, Any],
    state: AgentState,
    idx: int,
    grounded_tool_names: Set[str],
) -> Dict[str, Any]:
    """Execute a single tool call and return state update (used by deterministic shortcut)."""
    # Inject task_id for observability and session management
    tool_params["_task_id"] = task_id

    tool_calls = list(state.get("tool_calls", []))
    step_tool_results = []
    verification_reports = list(state.get("verification_reports", []))
    recovery_decisions = list(state.get("recovery_decisions", []))

    # Initialize canonical execution state
    exec_state_data = state.get("execution_state")
    execution_state = ExecutionState.from_dict(exec_state_data) if exec_state_data else ExecutionState(task_id=task_id)
    execution_state.current_step = step_number

    # Validate tool exists
    tool = tool_registry.get(tool_name)
    if not tool:
        final_answer = f"Tool '{tool_name}' not found"
        step_output = {
            "step_number": step_number,
            "description": description,
            "output": final_answer,
            "tool_results": [{"success": False, "error": final_answer}],
        }
        steps = list(state.get("steps", []))
        steps.append(step_output)
    # ── Output Validation at Node Exit ────────────────────────────────
    result = {
        "steps": steps,
        "current_step_index": idx + 1,
        "tool_calls": tool_calls,
        "messages": [AIMessage(content=f"Step {step_number} result: {final_answer}")],
        "verification_reports": verification_reports,
        "recovery_decisions": recovery_decisions,
        "status": "step_executed",
        "execution_state": execution_state.to_dict(),
    }
    out_valid = await guardrails.verify_output({"status": result["status"], "output": final_answer[:500]})
    if not out_valid:
        logger.warning(f"[executor_node] Guardrail output validation failed for task {task_id} step {step_number}")
        result["error"] = "Executor guardrail validation failed"
        result["status"] = "guardrail_blocked"
    return result

    severity = SafetyGate().check_tool_call(tool_name, tool_params, state.get("query", ""))
    if severity == ActionSeverity.IRREVERSIBLE:
        await observability_bus.emit_safe(
            ObservabilityEventType.SAFETY_CHECK,
            task_id=task_id,
            trace_id=state.get("trace_id"),
            payload={"tool": tool_name, "severity": "irreversible", "params": tool_params},
            source="safety_gate",
        )
        # Block irreversible actions — return blocked result immediately
        blocked_error = f"Action blocked: '{tool_name}' is classified as irreversible. Human approval required."
        tool_result = {"success": False, "data": None, "error": blocked_error}
        tool_calls.append({
            "step": step_number,
            "tool": tool_name,
            "result": tool_result,
        })
        step_tool_results.append(tool_result)
        # Record blocked action in canonical state
        tool_record = ToolExecutionRecord.from_tool_result(tool_name, tool_result)
        execution_state.record_tool(step_number, description, tool_record)
        step_output = {
            "step_number": step_number,
            "description": description,
            "output": blocked_error,
            "tool_results": step_tool_results,
        }
        steps = state.get("steps", [])
        steps.append(step_output)
        result = {
            "steps": steps,
            "current_step_index": idx + 1,
            "tool_calls": tool_calls,
            "messages": [AIMessage(content=f"Step {step_number} BLOCKED: {blocked_error}")],
            "verification_reports": verification_reports,
            "recovery_decisions": recovery_decisions,
            "status": "blocked",
            "execution_state": execution_state.to_dict(),
        }
        return await _validate_node_output("executor_node", task_id, result, blocked_error)

    logger.info(f"[_execute_tool_call][TRACE] EXECUTING TOOL: tool_name='{tool_name}'")
    logger.info(f"[_execute_tool_call][TRACE] TOOL PAYLOAD: {json.dumps(tool_params, indent=2, default=str)}")
    await observability_bus.emit_safe(
        ObservabilityEventType.TOOL_INVOKED,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        step_id=str(step_number),
        payload={"tool": tool_name, "params": tool_params},
        source="executor_node",
    )
    try:
        tool_output = await tool_registry.execute(tool_name, tool_params)
        logger.info(f"[_execute_tool_call][TRACE] RAW TOOL RESPONSE: success={tool_output.success} result={tool_output.result} error={tool_output.error}")
        tool_result = {
            "success": tool_output.success,
            "data": tool_output.result if tool_output.result is not None else str(tool_output),
            "error": tool_output.error,
        }
    except Exception as e:
        logger.error(f"[_execute_tool_call][TRACE] Tool execution EXCEPTION: {e}")
        logger.error(f"[_execute_tool_call] Tool execution error: {e}")
        tool_result = {"success": False, "error": str(e)}

    tool_calls.append({
        "step": step_number,
        "tool": tool_name,
        "result": tool_result,
    })
    step_tool_results.append(tool_result)

    # Record in canonical execution state
    tool_record = ToolExecutionRecord.from_tool_result(tool_name, tool_result)
    execution_state.record_tool(step_number, description, tool_record)

    # Deterministic verification
    if tool_result["success"]:
        if "filesystem" in tool_name and tool_params.get("path"):
            v_report = await verification_engine.verify(
                task_id, None, "file_exists",
                {"path": tool_params["path"]},
            )
            verification_reports.append(v_report.model_dump())

    final_answer = tool_result.get("data", "") if tool_result["success"] else tool_result.get("error", "")
    if isinstance(final_answer, dict):
        final_answer = json.dumps(final_answer, indent=2, ensure_ascii=False)
    elif not isinstance(final_answer, str):
        final_answer = str(final_answer)
    step_output = {
        "step_number": step_number,
        "description": description,
        "output": final_answer,
        "tool_results": step_tool_results,
    }

    steps = list(state.get("steps", []))
    steps.append(step_output)

    await observability_bus.emit_safe(
        ObservabilityEventType.STEP_STARTED,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        step_id=str(step_number),
        payload={"status": "completed", "output_preview": str(final_answer)[:200]},
        source="executor_node",
    )

    result = {
        "steps": steps,
        "current_step_index": idx + 1,
        "tool_calls": tool_calls,
        "messages": [AIMessage(content=f"Step {step_number} result: {final_answer}")],
        "verification_reports": verification_reports,
        "recovery_decisions": recovery_decisions,
        "status": "step_executed",
        "execution_state": execution_state.to_dict(),
    }
    return await _validate_node_output("executor_node", task_id, result, str(final_answer)[:500])


async def verifier_node(state: AgentState) -> Dict[str, Any]:
    """Verify if the execution results satisfy the original query.

    Uses deterministic verification first, then LLM as fallback for semantic checks.
    """
    query = state.get("query", "")
    steps = state.get("steps", [])
    task_id = state.get("task_id", "")
    plan = state.get("plan", [])

    logger.info(f"[verifier_node] Verifying task {task_id}")

    if not steps:
        return {"verified": False, "verification_notes": "No steps were executed"}

    env_config = state.get("environment_config", {})
    env_type = env_config.get("environment", "local") if isinstance(env_config, dict) else getattr(env_config, "environment", "local")

    # ── Canonical Execution State (unified truth) ────────────────────
    exec_state_data = state.get("execution_state")
    execution_state = ExecutionState.from_dict(exec_state_data) if exec_state_data else None

    # ── Deterministic Verification ───────────────────────────────────
    det_reports = []
    det_pass = True
    try:
        # 1. Check canonical execution state first (terminal success = skip re-verification)
        if execution_state and execution_state.has_any_terminal_success():
            det_pass = True
            det_reports = []
            logger.info(f"[verifier_node] Terminal success detected in execution_state; skipping re-verification")
        else:
            # 2. Fallback: check raw tool_calls for backwards compat
            tool_calls = state.get("tool_calls", []) or []
            open_app_calls = [
                t for t in tool_calls
                if t.get("tool") == "desktop_env__open_application"
                and t.get("result", {}).get("success")
                and isinstance(t.get("result", {}).get("data"), dict)
                and (t["result"]["data"].get("pid") or t["result"]["data"].get("window"))
            ]
            if open_app_calls:
                det_pass = True
                det_reports = []
                logger.info(f"[verifier_node] Successful open_application detected in tool_calls; skipping re-verification")
            elif env_type == "desktop":
                # Desktop block handles verify_plan with environment_config;
                # skip general verify_plan call to avoid double invocation.
                pass
            else:
                det_reports = await verification_engine.verify_plan(task_id, plan)
                for r in det_reports:
                    if r.result == VerificationResult.FAIL:
                        det_pass = False
                        break
    except Exception as e:
        logger.warning(f"[verifier_node] Deterministic verification error: {e}")

    # Update state with deterministic reports
    existing_reports = state.get("verification_reports", [])
    for r in det_reports:
        existing_reports.append(r.model_dump())

    # ── LLM Semantic Verification (skip for deterministic terminal success) ─
    llm_verified = False
    notes = ""
    if det_pass and execution_state and execution_state.has_any_terminal_success():
        # Deterministic terminal success is trusted; skip expensive LLM verification
        llm_verified = True
        notes = "Deterministic terminal success verified. Skipping LLM semantic check."
        logger.info(f"[verifier_node] Deterministic terminal success — skipping LLM verification")
    else:
        llm = get_llm_client()
        context = json.dumps({"query": query, "steps": steps}, indent=2, default=str)

        messages = [
            SystemMessage(content=VERIFIER_SYSTEM_PROMPT),
            HumanMessage(content=f"Context:\n{context}"),
        ]

        try:
            raw = await llm.complete_json(
                messages=_to_openai_messages(messages),
                response_schema={
                    "type": "object",
                    "properties": {
                        "verified": {"type": "boolean"},
                        "notes": {"type": "string"},
                    },
                    "required": ["verified", "notes"],
                },
            )
            llm_verified = raw.get("verified", False)
            notes = raw.get("notes", "")
        except Exception as e:
            logger.error(f"[verifier_node] LLM verification failed: {e}")
            llm_verified = False
            notes = f"LLM verification error: {e}"

    # Environment-specific verification
    env_verified = True
    env_notes = ""
    if env_type == "browser_ui":
        # Check canonical execution state first, then fall back to tool_calls
        browser_calls = []
        if execution_state:
            for step_rec in execution_state.steps.values():
                for tool_rec in step_rec.tools:
                    if tool_rec.tool_name.startswith("browser_env__"):
                        browser_calls.append(tool_rec.to_dict())
        if not browser_calls:
            tool_calls = state.get("tool_calls", [])
            browser_calls = [t for t in tool_calls if t.get("tool", "").startswith("browser_env__")]
        if not browser_calls:
            env_verified = False
            env_notes = "Browser environment selected but no browser_env tools were invoked."
        else:
            env_notes = f"Browser automation verified: {len(browser_calls)} browser actions performed."
    elif env_type == "cloud_api":
        # Check canonical execution state first, then fall back to tool_calls
        cloud_calls = []
        if execution_state:
            for step_rec in execution_state.steps.values():
                for tool_rec in step_rec.tools:
                    if tool_rec.tool_name.startswith("cloud__"):
                        cloud_calls.append(tool_rec.to_dict())
        if not cloud_calls:
            tool_calls = state.get("tool_calls", [])
            cloud_calls = [t for t in tool_calls if t.get("tool", "").startswith("cloud__")]
        if not cloud_calls:
            env_verified = False
            env_notes = "Cloud API environment selected but no cloud tools were invoked."
        else:
            env_notes = f"Cloud API verified: {len(cloud_calls)} API calls made."
    elif env_type == "desktop":
        # FR3.1: Call verification_engine.verify_plan() for desktop-specific
        # deterministic checks (desktop_app_opened, desktop_text_typed, etc.)
        # This ensures desktop verifiers run even when earlier det_pass
        # checks skip verify_plan (e.g., after open_application success).
        verification_notes_list = []
        desktop_verify_passed = True
        try:
            desktop_verify_reports = await verification_engine.verify_plan(
                task_id, plan,
                environment_config=env_config if isinstance(env_config, dict) else {}
            )
            for report in desktop_verify_reports:
                if report.result == VerificationResult.FAIL:
                    desktop_verify_passed = False
                    verification_notes_list.append(
                        report.failure_reason or "Desktop verification via verify_plan() failed"
                    )
                else:
                    check_type = report.checks[0].get("type", "unknown") if report.checks else "unknown"
                    verification_notes_list.append(
                        f"Desktop check '{check_type}': {report.result.value}"
                    )
            if len(desktop_verify_reports) == 0:
                # No desktop-specific verifications matched the plan;
                # rely on tool call check below to determine env_verified
                desktop_verify_passed = None
            else:
                env_verified = desktop_verify_passed
        except Exception as e:
            logger.warning(f"[verifier_node] Desktop verify_plan() error: {e}")
            verification_notes_list.append(f"Desktop verify_plan error: {e}")
            desktop_verify_passed = None
            # Fall through to tool call check

        # Fallback/Supplementary: Check if any desktop tool calls were made
        desktop_calls = []
        if execution_state:
            for step_rec in execution_state.steps.values():
                for tool_rec in step_rec.tools:
                    if tool_rec.tool_name.startswith(("desktop_env__", "desktop__")):
                        desktop_calls.append(tool_rec.to_dict())
        if not desktop_calls:
            tool_calls = state.get("tool_calls", [])
            desktop_calls = [t for t in tool_calls if t.get("tool", "").startswith(("desktop_env__", "desktop__"))]
        if not desktop_calls:
            env_verified = False
            env_notes = "Desktop environment selected but no desktop tools were invoked."
        elif desktop_verify_passed is None:
            # verify_plan() returned no reports — could not confirm state change
            env_verified = False
            env_notes = "Desktop tools were invoked but verify_plan() could not confirm state change."
        else:
            suffix = " " + " ".join(verification_notes_list) if verification_notes_list else ""
            env_notes = f"Desktop automation verified: {len(desktop_calls)} desktop actions performed.{suffix}"

    # Final verdict: both deterministic and LLM must agree for PASS
    verified = det_pass and llm_verified and env_verified
    logger.info(f"[verifier_node][TRACE] VERIFICATION RESULT: det_pass={det_pass} llm_verified={llm_verified} env_verified={env_verified} FINAL={verified}")
    logger.info(f"[verifier_node][TRACE] TOOL CALLS INSPECTED: {state.get('tool_calls', [])}")
    if not det_pass and llm_verified:
        notes = f"Deterministic checks failed but LLM thinks it's OK. {notes}"
    elif det_pass and not llm_verified:
        notes = f"Deterministic checks passed but semantic verification failed. {notes}"

    if env_notes:
        notes = f"{env_notes} {notes}"

    await observability_bus.emit_safe(
        ObservabilityEventType.VERIFICATION_COMPLETED,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        payload={"verified": verified, "notes": notes, "deterministic_pass": det_pass, "llm_verified": llm_verified, "env_verified": env_verified},
        source="verifier_node",
    )

    # ── Output Validation at Node Exit ────────────────────────────────
    result = {
        "verified": verified,
        "verification_notes": notes,
        "verification_reports": existing_reports,
        "messages": [AIMessage(content=f"Verification: {'PASS' if verified else 'FAIL'} — {notes}")],
        "status": "verification_complete",
    }
    return await _validate_node_output("verifier_node", task_id, result, notes)


async def approval_node(state: AgentState) -> Dict[str, Any]:
    """Pause execution for human approval using LangGraph interrupt."""
    task_id = state.get("task_id", "")
    step = state.get("steps", [{}])[-1]
    logger.info(f"[approval_node] Requesting approval for task {task_id}")

    # ── Per-session approval mode check ───────────────────────────────
    from ..safety.approval_store import approval_store
    mode = approval_store.get_mode(task_id)
    if mode.value == "full_trust":
        logger.info(f"[approval_node] Full-trust mode active for task {task_id}. Auto-approving.")
        approval_store.log_auto_approval(task_id, "final_verification", {}, "full_trust_verification")
        result = {
            "approved": True,
            "approval_reason": "Auto-approved: full-trust session mode",
            "messages": [AIMessage(content="Auto-approved: full-trust session mode")],
            "status": "approved",
        }
        return await _validate_node_output("approval_node", task_id, result, "Auto-approved: full-trust session mode")

    # LangGraph interrupt pauses the graph and stores the checkpoint
    # The value returned here is what gets passed when the graph is resumed
    value = interrupt({
        "task_id": task_id,
        "step": step,
        "message": "Approval required before proceeding",
    })

    # value is the user's response when resumed
    approved = value.get("approved", False) if isinstance(value, dict) else False
    reason = value.get("reason", "") if isinstance(value, dict) else str(value)

    logger.info(f"[approval_node] Approval result for task {task_id}: {approved}")
    await observability_bus.emit_safe(
        ObservabilityEventType.SAFETY_CHECK,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        payload={"approved": approved, "reason": reason},
        source="approval_node",
    )

    result = {
        "approved": approved,
        "approval_reason": reason,
        "messages": [AIMessage(content=f"Approval {'granted' if approved else 'denied'}: {reason}")],
        "status": "approved" if approved else "rejected",
    }
    return await _validate_node_output("approval_node", task_id, result, f"Approval {'granted' if approved else 'denied'}: {reason}")


async def summarizer_node(state: AgentState) -> Dict[str, Any]:
    """Compile final result from all executed steps using LLM summarization."""
    query = state.get("query", "")
    steps = state.get("steps", [])
    task_id = state.get("task_id", "")

    logger.info(f"[summarizer_node] Summarizing task {task_id}")

    outputs = []
    for s in steps:
        out = s.get("output", "")
        if isinstance(out, dict):
            out = json.dumps(out, indent=2, ensure_ascii=False)
        elif not isinstance(out, str):
            out = str(out)
        outputs.append(out)
    combined = "\n\n".join(outputs)

    # Use LLM to produce a concise user-facing summary
    llm = get_llm_client()
    summary_prompt = f"""Summarize the following task execution results into a concise, user-friendly response.

Original query: {query}

Step outputs:
{combined}

Provide a brief summary (2-4 sentences) of what was accomplished and any important notes."""

    try:
        summary_response = await llm.complete_json(
            messages=[{"role": "user", "content": summary_prompt}],
            response_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
            },
        )
        summary = summary_response.get("summary", combined[:1000])
    except Exception as e:
        logger.warning(f"[summarizer_node] LLM summarization failed: {e}")
        summary = combined[:1000]

    await observability_bus.emit_safe(
        ObservabilityEventType.TASK_COMPLETED,
        task_id=task_id,
        trace_id=state.get("trace_id"),
        payload={"steps_executed": len(steps), "summary": summary[:200]},
        source="summarizer_node",
    )

    # ── Output Validation at Node Exit ────────────────────────────────
    result = {
        "result": {
            "query": query,
            "steps_executed": len(steps),
            "outputs": outputs,
            "summary": summary,
            "trace_id": state.get("trace_id", ""),
        },
        "messages": [AIMessage(content=f"Task complete. Summary:\n{summary}")],
        "status": "completed",
    }
    return await _validate_node_output("summarizer_node", task_id, result, summary)
