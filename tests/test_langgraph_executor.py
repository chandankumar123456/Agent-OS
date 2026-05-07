"""Tests for LangGraph executor node tool invocation."""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from app.langgraph.nodes import executor_node, planner_node
from app.langgraph.state import AgentState


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_executor_node_invokes_tool_when_llm_requests_it(mock_obs_bus):
    """Executor should call a tool when the LLM returns a tool_call JSON."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
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

        with patch("app.langgraph.nodes.tool_grounding_layer") as mock_grounding:
            mock_grounding.filter_tools_for_step = MagicMock(return_value=[
                {
                    "name": "filesystem__write_file",
                    "description": "Write a file",
                    "parameters": {"properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
                }
            ])
            with patch("app.langgraph.nodes.tool_registry") as mock_registry:
                mock_registry.discover_mcp_tools = AsyncMock()
                mock_registry.list_tools = MagicMock(return_value=[
                    {
                        "name": "filesystem__write_file",
                        "description": "Write a file",
                        "parameters": {"properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
                    }
                ])
                mock_registry.get = MagicMock(return_value=AsyncMock())
                mock_tool_output = AsyncMock()
                mock_tool_output.success = True
                mock_tool_output.result = {"output": "File written: /tmp/test.txt"}
                mock_tool_output.error = None
                mock_registry.execute = AsyncMock(return_value=mock_tool_output)

            with patch("app.langgraph.nodes.recovery_engine") as mock_recovery:
                mock_decision = MagicMock()
                mock_decision.action = MagicMock(value="retry")
                mock_decision.reason = "Mock recovery"
                mock_decision.next_tool = None
                mock_decision.model_dump = MagicMock(return_value={"action": "retry", "reason": "Mock recovery", "next_tool": None})
                mock_recovery.decide = AsyncMock(return_value=mock_decision)
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
    mock_registry.execute.assert_called_once_with("filesystem__write_file", {"path": "/tmp/test.txt", "content": "hello", "_task_id": "test-task"})


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_executor_node_falls_back_to_answer_without_tool(mock_obs_bus):
    """Executor should return answer directly when no tool is needed."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
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
            mock_registry.list_tools = MagicMock(return_value=[])
            mock_registry.get = MagicMock(return_value=None)
            mock_registry.execute = AsyncMock()

            result = await executor_node(state)

    assert result["status"] == "step_executed"
    assert result["steps"][0]["output"] == "4"
    assert len(result["steps"][0]["tool_results"]) == 0
    mock_registry.execute.assert_not_called()


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_planner_node_produces_valid_plan(mock_obs_bus):
    """Planner should return a plan with all required fields."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
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

    with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm, \
         patch("app.langgraph.nodes.workflow_decomposer.decompose") as mock_decompose:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(return_value=mock_plan)
        mock_get_llm.return_value = mock_llm
        mock_decompose.return_value = []  # force LLM fallback

        result = await planner_node(state)

    assert result["status"] == "planning_complete"
    assert len(result["plan"]) == 1
    assert result["plan"][0]["tool"] == "filesystem__write_file"
    assert result["plan"][0]["expected_output"] == "file created"
