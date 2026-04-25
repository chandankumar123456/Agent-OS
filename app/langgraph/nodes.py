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
from .state import AgentState


def _to_openai_messages(messages):
    """Map LangChain message types to OpenAI roles."""
    role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
    return [{"role": role_map.get(m.type, m.type), "content": m.content} for m in messages]


PLANNER_SYSTEM_PROMPT = """You are an expert planning agent. Given a user query, break it down into a clear, ordered list of steps.
Each step should specify:
- step_number: integer starting at 1
- description: what to do
- tool: tool name to use (or null if no tool needed)
- expected_output: what the step should produce

Respond ONLY with valid JSON in this format:
{"plan": [{"step_number": 1, "description": "...", "tool": "...", "expected_output": "..."}]}
"""


VERIFIER_SYSTEM_PROMPT = """You are a verification agent. Given a user query, the execution plan, and the results, verify if the task was completed successfully.

Respond ONLY with valid JSON:
{"verified": true/false, "notes": "explanation of verification result"}
"""


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """Generate an execution plan from the user query."""
    query = state.get("query", "")
    logger.info(f"[planner_node] Planning for task {state.get('task_id')}")

    llm = get_llm_client()
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
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

    # Discover tools and build execution prompt
    await tool_registry.discover_mcp_tools()
    available_tools = tool_registry.list_tools()
    tools_json = json.dumps(available_tools, indent=2, default=str)

    os_info = f"{platform.system()} {platform.release()}"
    system_prompt = f"""You are an execution agent. Your job is to CARRY OUT the given step by any means necessary.
You have access to the following tools. You MUST use a tool when the step requires interacting with the filesystem, running code, using a calculator, searching the web, or executing shell commands.

Available tools:
{tools_json}

Current operating system: {os_info}

CRITICAL RULES:
1. If the step asks you to create, write, read, or modify a file, you MUST use the filesystem tool (e.g., filesystem__write_file, filesystem__read_file).
2. If the step asks you to run a command or script, you MUST use the shell tool (e.g., shell__execute_command, shell__run_script).
3. If the step asks you to browse or scrape the web, you MUST use the browser tool (e.g., browser__http_request, browser__scrape_page).
4. If the step requires calculation, use the calculator tool.
5. Do NOT just describe what you would do — actually invoke the tool with concrete parameters.
6. Use exact parameter names from the tool schema.
7. When creating files on Windows, use backslashes or raw strings for paths (e.g., C:\\Users\\Name\\Desktop\\file.txt). On Linux/macOS, use forward slashes.
8. The filesystem server restricts writes to the current working directory and the user's home directory. Use full absolute paths.

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

            tool_calls.append({
                "step": step_number,
                "tool": tool_name,
                "result": tool_result,
            })
            step_tool_results.append(tool_result)

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
        "status": "step_executed",
    }


async def verifier_node(state: AgentState) -> Dict[str, Any]:
    """Verify if the execution results satisfy the original query."""
    query = state.get("query", "")
    steps = state.get("steps", [])
    task_id = state.get("task_id", "")

    logger.info(f"[verifier_node] Verifying task {task_id}")

    if not steps:
        return {"verified": False, "verification_notes": "No steps were executed"}

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
        verified = raw.get("verified", False)
        notes = raw.get("notes", "")
    except Exception as e:
        logger.error(f"[verifier_node] Verification failed: {e}")
        verified = False
        notes = f"Verification error: {e}"

    return {
        "verified": verified,
        "verification_notes": notes,
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
