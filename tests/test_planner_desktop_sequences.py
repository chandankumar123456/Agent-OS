import pytest
from unittest.mock import AsyncMock, patch

from app.langgraph.nodes import planner_node
from app.langgraph.state import AgentState


@pytest.fixture
def planner_tools():
    return [
        {"name": "desktop_env__open_application"},
        {"name": "desktop_env__launch_app_and_open_file"},
        {"name": "desktop_env__get_window_list"},
        {"name": "desktop_env__focus_window"},
        {"name": "desktop_env__type_text"},
        {"name": "desktop_env__screenshot"},
        {"name": "desktop__get_ui_tree"},
        {"name": "browser_env__launch"},
        {"name": "browser_env__search"},
        {"name": "browser_env__screenshot"},
        {"name": "browser_env__get_text"},
        {"name": "filesystem__write_file"},
        {"name": "shell__execute_command"},
    ]


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
@patch("app.langgraph.nodes.tool_registry")
async def test_planner_open_notepad_and_type_hello_world(mock_tool_registry, mock_obs_bus, planner_tools):
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
    mock_tool_registry.list_tools.return_value = planner_tools

    state = AgentState(
        task_id="t-1",
        user_id="u-1",
        query="open notepad and type hello world",
        plan=[],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )
    result = await planner_node(state)
    plan = result["plan"]

    assert len(plan) == 5
    assert all(step["step_type"] == "desktop_automation" for step in plan)
    assert "open notepad" in plan[0]["description"].lower()
    assert "desktop_env__open_application" in plan[0]["allowed_tools"]
    assert "desktop_env__launch_app_and_open_file" in plan[0]["allowed_tools"]


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
@patch("app.langgraph.nodes.tool_registry")
async def test_planner_open_notepad_and_type_opinion_adds_content_generation(mock_tool_registry, mock_obs_bus, planner_tools):
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
    mock_tool_registry.list_tools.return_value = planner_tools

    state = AgentState(
        task_id="t-2",
        user_id="u-1",
        query="open notepad and type your opinion on avengers doomsday vs secret wars",
        plan=[],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )
    result = await planner_node(state)
    plan = result["plan"]
    step_types = [step["step_type"] for step in plan]

    assert len(plan) == 6
    assert step_types[2] == "content_generation"
    assert "generate the text content requested by the user" in plan[2]["description"].lower()
    assert step_types[4] == "desktop_automation"
    assert "type the requested text into notepad" in plan[4]["description"].lower()


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
@patch("app.langgraph.nodes.tool_registry")
async def test_planner_open_chrome_and_search_latest_ai_news(mock_tool_registry, mock_obs_bus, planner_tools):
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
    mock_tool_registry.list_tools.return_value = planner_tools

    state = AgentState(
        task_id="t-3",
        user_id="u-1",
        query="open chrome and search latest AI news",
        plan=[],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )
    result = await planner_node(state)
    plan = result["plan"]

    assert len(plan) == 4
    assert all(step["step_type"] == "browser_navigation" for step in plan)
    assert "open the browser" in plan[0]["description"].lower()
    assert "search for the requested query" in plan[2]["description"].lower()
