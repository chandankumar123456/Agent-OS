"""Tests for LangGraph executor node tool invocation."""
import pytest
import json
from unittest.mock import AsyncMock, patch

from app.langgraph.nodes import executor_node, planner_node
from app.langgraph.state import AgentState


@pytest.mark.asyncio
async def test_executor_node_invokes_tool_when_llm_requests_it():
    """Executor should call a tool when the LLM returns a tool_call JSON."""
    state = AgentState(
        task_id="test-task",
        user_id="user-1",
        query="write hello to /tmp/test.txt",
        plan=[{
            "step_number": 1,
            "description": "write hello to /tmp/test.txt",
            "tool": None,
            "expected_output": "file created",
        }],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )

    # Mock LLM to first return a tool call, then a direct answer
    mock_llm_responses = [
        {"tool_call": {"name": "filesystem__write_file", "params": {"path": "/tmp/test.txt", "content": "hello"}}},
        {"answer": "File written successfully", "details": "Created /tmp/test.txt"},
    ]

    with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(side_effect=mock_llm_responses)
        mock_get_llm.return_value = mock_llm

        with patch("app.langgraph.nodes.tool_registry") as mock_registry:
            mock_registry.discover_mcp_tools = AsyncMock()
            mock_registry.list_tools = AsyncMock(return_value=[
                {
                    "name": "filesystem__write_file",
                    "description": "Write a file",
                    "parameters": {"properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
                }
            ])
            mock_registry.get = AsyncMock(return_value=AsyncMock())
            mock_tool_output = AsyncMock()
            mock_tool_output.success = True
            mock_tool_output.result = {"output": "File written: /tmp/test.txt"}
            mock_tool_output.error = None
            mock_registry.execute = AsyncMock(return_value=mock_tool_output)

            result = await executor_node(state)

    assert result["status"] == "step_executed"
    assert result["current_step_index"] == 1
    assert len(result["steps"]) == 1
    step = result["steps"][0]
    assert step["step_number"] == 1
    assert step["output"] == "File written successfully"
    assert len(step["tool_results"]) == 1
    assert step["tool_results"][0]["success"] is True
    assert len(result["tool_calls"]) == 1
    mock_registry.execute.assert_called_once_with("filesystem__write_file", {"path": "/tmp/test.txt", "content": "hello"})


@pytest.mark.asyncio
async def test_executor_node_falls_back_to_answer_without_tool():
    """Executor should return answer directly when no tool is needed."""
    state = AgentState(
        task_id="test-task",
        user_id="user-1",
        query="what is 2+2",
        plan=[{
            "step_number": 1,
            "description": "Calculate 2+2",
            "tool": None,
            "expected_output": "4",
        }],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )

    with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(return_value={"answer": "4", "details": "2+2=4"})
        mock_get_llm.return_value = mock_llm

        with patch("app.langgraph.nodes.tool_registry") as mock_registry:
            mock_registry.discover_mcp_tools = AsyncMock()
            mock_registry.list_tools = AsyncMock(return_value=[])
            mock_registry.get = AsyncMock(return_value=None)
            mock_registry.execute = AsyncMock()

            result = await executor_node(state)

    assert result["status"] == "step_executed"
    assert result["steps"][0]["output"] == "4"
    assert len(result["steps"][0]["tool_results"]) == 0
    mock_registry.execute.assert_not_called()


@pytest.mark.asyncio
async def test_planner_node_produces_valid_plan():
    """Planner should return a plan with all required fields."""
    state = AgentState(
        task_id="test-task",
        user_id="user-1",
        query="create a file on desktop",
        plan=[],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )

    mock_plan = {
        "plan": [
            {
                "step_number": 1,
                "description": "Create a file on the desktop",
                "tool": "filesystem__write_file",
                "expected_output": "file created",
            }
        ]
    }

    with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(return_value=mock_plan)
        mock_get_llm.return_value = mock_llm

        result = await planner_node(state)

    assert result["status"] == "planning_complete"
    assert len(result["plan"]) == 1
    assert result["plan"][0]["tool"] == "filesystem__write_file"
    assert result["plan"][0]["expected_output"] == "file created"
