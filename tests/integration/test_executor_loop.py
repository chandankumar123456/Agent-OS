import pytest
from app.langgraph.nodes import executor_node
from app.langgraph.state import AgentState


@pytest.mark.asyncio
async def test_executor_injects_prior_steps():
    state: AgentState = {
        "query": "test query",
        "task_id": "test-task",
        "user_id": "test-user",
        "trace_id": "trace-123",
        "config": {},
        "messages": [],
        "plan": [
            {"step_number": 1, "description": "Launch browser", "tool": "browser_env__launch", "expected_output": "Browser open"},
            {"step_number": 2, "description": "Navigate to example.com", "tool": "browser_env__navigate", "expected_output": "Page loaded"},
        ],
        "steps": [
            {"step_number": 1, "description": "Launch browser", "output": "Browser launched", "tool_results": [{"success": True}]},
        ],
        "step_results": {},
        "current_step_index": 1,
        "tool_calls": [],
        "verified": False,
        "verification_notes": None,
        "approved": None,
        "approval_reason": None,
        "result": {},
        "error": None,
        "capability_assessment": None,
        "feasibility_report": None,
        "environment_config": None,
        "verification_reports": [],
        "recovery_decisions": [],
        "created_at": "2026-01-01T00:00:00",
        "mode": "task",
        "status": "pending",
        "max_tool_rounds": 5,
    }

    result = await executor_node(state)
    assert result["status"] == "step_executed"
    assert result["current_step_index"] == 2
