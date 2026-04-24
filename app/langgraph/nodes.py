"""LangGraph node functions for AgentOS agent execution."""
import json
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt

from ..agents.llm_client import get_llm_client
from ..logs.logger import logger
from ..tools.registry import tool_registry
from .state import AgentState


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
            messages=[{"role": m.type, "content": m.content} for m in messages],
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
                            "required": ["step_number", "description"],
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
    """Execute the current step using available tools."""
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    task_id = state.get("task_id", "")

    if idx >= len(plan):
        logger.info(f"[executor_node] All steps complete for task {task_id}")
        return {"status": "execution_complete"}

    step = plan[idx]
    step_number = step.get("step_number", idx + 1)
    description = step.get("description", "")
    tool_name = step.get("tool")

    logger.info(f"[executor_node] Executing step {step_number} for task {task_id}: {description}")

    # If a tool is specified, try to run it
    tool_result = None
    if tool_name:
        try:
            # Get tool from unified registry (built-in + MCP)
            tool = tool_registry.get(tool_name)
            if tool:
                parameters = {"query": description, **state.get("config", {})}
                tool_output = await tool_registry.execute(tool_name, parameters)
                tool_result = {
                    "success": tool_output.success,
                    "data": tool_output.data if hasattr(tool_output, "data") else str(tool_output),
                    "error": tool_output.error if hasattr(tool_output, "error") else None,
                }
            else:
                tool_result = {"success": False, "error": f"Tool '{tool_name}' not found"}
        except Exception as e:
            logger.error(f"[executor_node] Tool execution error: {e}")
            tool_result = {"success": False, "error": str(e)}

    # Build context for LLM
    tool_calls = state.get("tool_calls", [])
    if tool_result:
        tool_calls.append({
            "step": step_number,
            "tool": tool_name,
            "result": tool_result,
        })

    # Ask LLM to process step result
    llm = get_llm_client()
    context_msg = f"Step {step_number}: {description}"
    if tool_result:
        context_msg += f"\nTool result: {json.dumps(tool_result, indent=2)}"

    messages = [
        SystemMessage(content="You are an execution agent. Process the current step and produce output."),
        HumanMessage(content=context_msg),
    ]

    try:
        response = await llm.complete(
            messages=[{"role": m.type, "content": m.content} for m in messages]
        )
    except Exception as e:
        logger.error(f"[executor_node] LLM execution failed: {e}")
        response = f"Error during execution: {e}"

    step_output = {
        "step_number": step_number,
        "description": description,
        "output": response,
        "tool_result": tool_result,
    }

    steps = state.get("steps", [])
    steps.append(step_output)

    return {
        "steps": steps,
        "current_step_index": idx + 1,
        "tool_calls": tool_calls,
        "messages": [AIMessage(content=f"Step {step_number} result: {response}")],
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
            messages=[{"role": m.type, "content": m.content} for m in messages],
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
