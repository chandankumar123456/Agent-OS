"""Tests for LangGraph state definitions."""
import pytest
from core.langgraph.state import AgentState


def test_agent_state_has_required_fields():
    state = AgentState(
        task_id="test-task",
        user_id="user-1",
        trace_id="trace-1",
        query="What is the weather?",
        config={"mode": "task"},
        messages=[],
        plan=[],
        current_step_index=0,
        steps=[],
        step_results={},
        tool_calls=[],
        verified=False,
        verification_notes=None,
        approved=None,
        approval_reason=None,
        result={},
        error=None,
        created_at="2024-01-01T00:00:00",
        mode="task",
        status="pending",
    )
    assert state["task_id"] == "test-task"
    assert state["query"] == "What is the weather?"
    assert state["status"] == "pending"
    assert state["messages"] == []


def test_agent_state_is_total_false_allows_partial():
    # TypedDict with total=False should allow partial construction
    state = AgentState(task_id="t1", query="hello")
    assert state["task_id"] == "t1"
    assert state["query"] == "hello"
    assert "status" not in state
