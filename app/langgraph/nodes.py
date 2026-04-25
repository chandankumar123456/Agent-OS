"""LangGraph node functions for AgentOS agent execution."""
import json
import os
import platform
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt

from ..agents.llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.registry import tool_registry
from ..capabilities import verification_engine, recovery_engine
from ..capabilities.models import VerificationResult, RecoveryAction
from .state import AgentState


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


PLANNER_SYSTEM_PROMPT_TEMPLATE = """You are an expert planning agent. Given a user query, break it down into a clear, ordered list of steps.
Each step should specify:
- step_number: integer starting at 1
- description: what to do (be specific about file paths and tool names)
- tool: tool name to use (or null if no tool needed)
- expected_output: what the step should produce

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
{{"plan": [{{"step_number": 1, "description": "...", "tool": "...", "expected_output": "..."}}]}}
"""


VERIFIER_SYSTEM_PROMPT = """You are a verification agent. Given a user query, the execution plan, and the results, verify if the task was completed successfully.

Respond ONLY with valid JSON:
{"verified": true/false, "notes": "explanation of verification result"}
"""


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Generate an execution plan from the user query, informed by capability assessment."""
    query = state.get("query", "")
    task_id = state.get("task_id", "")
    logger.info(f"[planner_node] Planning for task {task_id}")

    os_info = f"{platform.system()} {platform.release()}"
    home_path = os.path.expanduser("~")
    desktop_path = _get_desktop_path()

    # Inject capability assessment into prompt if available
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
                                "tool": {"type": ["string", "null"]},
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

    return {
        "plan": plan,
        "current_step_index": 0,
        "messages": [AIMessage(content=f"Plan: {json.dumps(plan, indent=2)}")],
        "status": "planning_complete",
    }


async def executor_node(state: AgentState) -> Dict[str, Any]:
    """Execute the current step using available tools via LLM-driven selection."""
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    task_id = state.get("task_id", "")

    if idx >= len(plan):
        logger.info(f"[executor_node] All steps complete for task {task_id}")
        return {"status": "execution_complete"}

    step = plan[idx]
    step_number = step.get("step_number", idx + 1)
    description = step.get("description", "")
    suggested_tool = step.get("tool")

    logger.info(f"[executor_node] Executing step {step_number} for task {task_id}: {description}")

    # Tools should already be discovered by orchestrator entry point.
    # Do NOT call discover_mcp_tools() here to avoid redundant work per step.
    available_tools = tool_registry.list_tools()
    tools_json = json.dumps(available_tools, indent=2, default=str)

    os_info = f"{platform.system()} {platform.release()}"
    home = os.path.expanduser("~")
    desktop_path = os.path.join(home, "Desktop")
    system_prompt = f"""You are an execution agent. Your job is to CARRY OUT the given step by any means necessary.
You have access to the following tools. You MUST use a tool when the step requires interacting with the filesystem, running code, using a calculator, searching the web, or executing shell commands.

Available tools:
{tools_json}

Current operating system: {os_info}
User home directory: {home}
User Desktop path: {desktop_path}

CRITICAL RULES:
1. If the step asks you to create, write, read, or modify a file, you MUST use the filesystem tool (e.g., filesystem__write_file, filesystem__read_file).
2. If the step asks you to run a command or script, you MUST use the shell tool (e.g., shell__execute_command, shell__run_script).
3. If the step asks you to browse or scrape the web, you MUST use the browser tool (e.g., browser__http_request, browser__scrape_page).
4. If the step requires calculation, use the calculator tool.
5. Do NOT just describe what you would do — actually invoke the tool with concrete parameters.
6. Use exact parameter names from the tool schema.
7. ALWAYS use ABSOLUTE file paths. NEVER use relative paths like ./file.py.
8. When creating files on Windows, use backslashes in paths (e.g., C:\\Users\\Name\\Desktop\\file.txt). On Linux/macOS, use forward slashes.
9. If the user asks for "desktop", use the Desktop path provided above.

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

    MAX_ROUNDS = 3
    tool_calls = state.get("tool_calls", [])
    step_tool_results = []
    final_answer = ""
    verification_reports = state.get("verification_reports", [])
    recovery_decisions = state.get("recovery_decisions", [])

    for round_num in range(MAX_ROUNDS):
        try:
            # Use json_object (no strict schema) so LLM can choose between tool_call and answer
            response = await get_llm_client().complete_json(
                messages=_to_openai_messages(messages)
            )
        except Exception as e:
            logger.error(f"[executor_node] LLM execution failed: {e}")
            final_answer = f"Error during execution: {e}"
            break

        tool_call = response.get("tool_call")
        if tool_call and isinstance(tool_call, dict):
            tool_name = tool_call.get("name")
            tool_params = tool_call.get("params", {})

            if not tool_name:
                final_answer = response.get("answer") or response.get("details") or json.dumps(response)
                break

            # Validate tool exists
            tool = tool_registry.get(tool_name)
            if not tool:
                error_msg = f"Tool '{tool_name}' not found"
                logger.error(f"[executor_node] {error_msg}")
                messages.append(AIMessage(content=json.dumps(response)))
                messages.append(HumanMessage(content=f"Error: {error_msg}. Use a valid tool or provide a direct answer."))
                continue

            logger.info(f"[executor_node] Invoking tool '{tool_name}' with params: {tool_params}")
            try:
                tool_output = await tool_registry.execute(tool_name, tool_params)
                tool_result = {
                    "success": tool_output.success,
                    "data": tool_output.result if tool_output.result is not None else str(tool_output),
                    "error": tool_output.error,
                }
            except Exception as e:
                logger.error(f"[executor_node] Tool execution error: {e}")
                tool_result = {"success": False, "error": str(e)}

            # Always record tool result first
            tool_calls.append({
                "step": step_number,
                "tool": tool_name,
                "result": tool_result,
            })
            step_tool_results.append(tool_result)

            # ── Deterministic Verification ─────────────────────────────
            if tool_result["success"]:
                # Auto-verify based on tool type
                if "filesystem" in tool_name and tool_params.get("path"):
                    v_report = await verification_engine.verify(
                        task_id, None, "file_exists",
                        {"path": tool_params["path"]},
                    )
                    verification_reports.append(v_report.model_dump())
                    if v_report.result == VerificationResult.FAIL:
                        # Trigger recovery for next iteration
                        decision = recovery_engine.decide(
                            task_id, None,
                            error=v_report.failure_reason,
                            verification_report=v_report,
                            current_tool=tool_name,
                        )
                        recovery_decisions.append(decision.model_dump())
                        if decision.action == RecoveryAction.SWITCH_TOOL and decision.next_tool:
                            messages.append(HumanMessage(
                                content=f"Verification failed. Switching to alternative tool: {decision.next_tool}"
                            ))
                            # Continue to next round with new tool instruction
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

    step_output = {
        "step_number": step_number,
        "description": description,
        "output": final_answer,
        "tool_results": step_tool_results,
    }

    steps = state.get("steps", [])
    steps.append(step_output)

    return {
        "steps": steps,
        "current_step_index": idx + 1,
        "tool_calls": tool_calls,
        "messages": [AIMessage(content=f"Step {step_number} result: {final_answer}")],
        "verification_reports": verification_reports,
        "recovery_decisions": recovery_decisions,
        "status": "step_executed",
    }


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

    # ── Deterministic Verification ───────────────────────────────────
    det_reports = []
    det_pass = True
    try:
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

    # If deterministic checks all pass, we still run LLM for semantic validation
    # If they fail, we can short-circuit unless recovery already handled it

    # ── LLM Semantic Verification ────────────────────────────────────
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

    # Final verdict: both deterministic and LLM must agree for PASS
    verified = det_pass and llm_verified
    if not det_pass and llm_verified:
        notes = f"Deterministic checks failed but LLM thinks it's OK. {notes}"
    elif det_pass and not llm_verified:
        notes = f"Deterministic checks passed but semantic verification failed. {notes}"

    return {
        "verified": verified,
        "verification_notes": notes,
        "verification_reports": existing_reports,
        "messages": [AIMessage(content=f"Verification: {'PASS' if verified else 'FAIL'} — {notes}")],
        "status": "verification_complete",
    }


async def approval_node(state: AgentState) -> Dict[str, Any]:
    """Pause execution for human approval using LangGraph interrupt."""
    task_id = state.get("task_id", "")
    step = state.get("steps", [{}])[-1]
    logger.info(f"[approval_node] Requesting approval for task {task_id}")

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

    return {
        "approved": approved,
        "approval_reason": reason,
        "messages": [AIMessage(content=f"Approval {'granted' if approved else 'denied'}: {reason}")],
        "status": "approved" if approved else "rejected",
    }


async def summarizer_node(state: AgentState) -> Dict[str, Any]:
    """Compile final result from all executed steps."""
    query = state.get("query", "")
    steps = state.get("steps", [])
    task_id = state.get("task_id", "")

    logger.info(f"[summarizer_node] Summarizing task {task_id}")

    # Compile outputs
    outputs = [s.get("output", "") for s in steps]
    combined = "\n\n".join(outputs)

    return {
        "result": {
            "query": query,
            "steps_executed": len(steps),
            "outputs": outputs,
            "summary": combined,
            "trace_id": state.get("trace_id", ""),
        },
        "messages": [AIMessage(content=f"Task complete. Summary:\n{combined}")],
        "status": "completed",
    }
