"""Integration test for the target workflow:

'open file explorer, find my major project report, summarize it, create HTML/CSS/JS files, and open it in Chrome'

This test verifies:
1. Planner produces structured steps with correct step_type, allowed_tools, fallback_tools.
2. No hybrid steps (mixing browser/desktop/filesystem in one step).
3. Filesystem tools are preferred for local file tasks.
4. Executor obeys planner's allowed_tools and does not re-ground.
5. Dependency failures halt the workflow.
6. No false 'filesystem tools unavailable' errors.
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from app.langgraph.nodes import executor_node, planner_node
from app.langgraph.state import AgentState


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_target_workflow_planner_produces_clean_steps(mock_obs_bus):
    """Planner must emit isolated filesystem-first steps for the target query."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
    query = "open file explorer, find my major project report, summarize it, create HTML/CSS/JS files, and open it in Chrome"
    state = AgentState(
        task_id="target-task",
        user_id="user-1",
        query=query,
        plan=[],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )

    with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm:
        # Force deterministic decomposition (no LLM fallback)
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(return_value={"plan": []})
        mock_get_llm.return_value = mock_llm

        result = await planner_node(state)

    assert result["status"] == "planning_complete"
    plan = result["plan"]
    assert len(plan) >= 4, f"Expected at least 4 phases, got {len(plan)}: {[p.get('step_type') for p in plan]}"

    # Verify no desktop_automation phase is emitted for "open file explorer"
    step_types = [p.get("step_type") for p in plan]
    assert "desktop_automation" not in step_types, (
        f"Desktop automation should not appear for file discovery query. Got steps: {step_types}"
    )

    # Verify file steps are filesystem-only
    for step in plan:
        st = step.get("step_type")
        allowed = step.get("allowed_tools", [])
        if st in ("file_search", "file_read", "document_processing", "content_generation"):
            for tool in allowed:
                assert not tool.startswith("browser_env__"), (
                    f"Step {step['step_number']} ({st}) must not contain browser tools. Got {allowed}"
                )
                assert not tool.startswith("desktop_env__"), (
                    f"Step {step['step_number']} ({st}) must not contain desktop tools. Got {allowed}"
                )

    # Verify browser_open step uses browser/shell tools, not filesystem
    browser_steps = [s for s in plan if s.get("step_type") == "browser_open"]
    if browser_steps:
        for tool in browser_steps[-1].get("allowed_tools", []):
            assert not tool.startswith("filesystem__"), (
                f"browser_open step must not contain filesystem tools. Got {browser_steps[-1]['allowed_tools']}"
            )

    # Verify required flags are set on the file chain
    for step in plan:
        if step.get("step_type") in ("file_search", "file_read", "document_processing", "content_generation"):
            assert step.get("required") is True, (
                f"Step {step['step_number']} ({step['step_type']}) should be required"
            )


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_target_workflow_executor_obeys_allowed_tools(mock_obs_bus):
    """Executor must use only tools from the planner's allowed_tools list."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
    query = "find my major project report, summarize it, create HTML/CSS/JS files, and open it in Chrome"

    plan = [
        {
            "step_number": 1,
            "description": "Search filesystem for major project report",
            "step_type": "file_search",
            "tool": "filesystem__search_files",
            "allowed_tools": ["filesystem__search_files", "filesystem__list_directory"],
            "fallback_tools": ["shell__execute_command"],
            "expected_output": "report path",
            "required": True,
            "depends_on": [],
        },
        {
            "step_number": 2,
            "description": "Read the report file",
            "step_type": "file_read",
            "tool": "filesystem__read_file",
            "allowed_tools": ["filesystem__read_file"],
            "fallback_tools": [],
            "expected_output": "report content",
            "required": True,
            "depends_on": [1],
        },
    ]

    state = AgentState(
        task_id="target-task",
        user_id="user-1",
        query=query,
        plan=plan,
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
    )

    mock_llm_responses = [
        {"tool_call": {"name": "filesystem__search_files", "params": {"path": "C:\\Users\\Name\\Desktop", "pattern": "*report*"}}},
        {"answer": "Found report at C:\\Users\\Name\\Desktop\\report.txt"},
    ]

    with patch("app.langgraph.nodes.get_llm_client") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.complete_json = AsyncMock(side_effect=mock_llm_responses)
        mock_get_llm.return_value = mock_llm

        with patch("app.langgraph.nodes.tool_registry") as mock_registry:
            mock_registry.list_tools = MagicMock(return_value=[
                {"name": "filesystem__search_files"},
                {"name": "filesystem__list_directory"},
                {"name": "filesystem__read_file"},
                {"name": "browser_env__navigate"},
                {"name": "desktop_env__click"},
            ])
            mock_registry.get = MagicMock(return_value=AsyncMock())
            mock_tool_output = AsyncMock()
            mock_tool_output.success = True
            mock_tool_output.result = {"matches": ["C:\\Users\\Name\\Desktop\\report.txt"]}
            mock_tool_output.error = None
            mock_registry.execute = AsyncMock(return_value=mock_tool_output)

            with patch("app.langgraph.nodes.verification_engine") as mock_verif:
                mock_verif.verify = AsyncMock(return_value=MagicMock(result="pass", model_dump=MagicMock(return_value={})))

                result = await executor_node(state)

    assert result["status"] == "step_executed"
    assert result["current_step_index"] == 1
    # Verify the executor invoked ONLY the allowed tool
    calls = mock_registry.execute.call_args_list
    assert len(calls) == 1
    assert calls[0][0][0] == "filesystem__search_files"


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_target_workflow_halts_on_dependency_failure(mock_obs_bus):
    """If file search (step 1) fails, step 2 must not run and workflow must halt."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)
    query = "find my major project report, summarize it, create HTML/CSS/JS files, and open it in Chrome"

    plan = [
        {
            "step_number": 1,
            "description": "Search filesystem for major project report",
            "step_type": "file_search",
            "tool": "filesystem__search_files",
            "allowed_tools": ["filesystem__search_files"],
            "fallback_tools": [],
            "expected_output": "report path",
            "required": True,
            "depends_on": [],
        },
        {
            "step_number": 2,
            "description": "Read the report file",
            "step_type": "file_read",
            "tool": "filesystem__read_file",
            "allowed_tools": ["filesystem__read_file"],
            "fallback_tools": [],
            "expected_output": "report content",
            "required": True,
            "depends_on": [1],
        },
    ]

    # Step 1 already failed in prior execution
    prior_steps = [
        {
            "step_number": 1,
            "description": "Search filesystem for major project report",
            "required": True,
            "tool_results": [{"success": False, "error": "No matches found"}],
        }
    ]

    state = AgentState(
        task_id="target-task",
        user_id="user-1",
        query=query,
        plan=plan,
        current_step_index=1,
        steps=prior_steps,
        tool_calls=[],
        messages=[],
    )

    with patch("app.langgraph.nodes.tool_registry") as mock_registry:
        mock_registry.execute = AsyncMock()
        result = await executor_node(state)

    # Workflow must halt
    assert result.get("error") is not None
    assert result["current_step_index"] == len(plan)
    assert "halted" in result["messages"][0].content.lower() or "failed" in result["status"]
    assert result["status"] == "failed"
    # Step 2 must NOT have been executed
    mock_registry.execute.assert_not_called()


@pytest.mark.asyncio
@patch("app.langgraph.nodes.observability_bus")
async def test_target_workflow_no_false_filesystem_unavailable(mock_obs_bus):
    """Executor must not falsely claim filesystem tools are unavailable when they are registered."""
    mock_obs_bus.emit_safe = AsyncMock(return_value=None)

    # Simulate ExecutorAgent-level check (used by PipelineExecutor / StepExecutor)
    from app.agents.executor import ExecutorAgent
    from app.agents.base import AgentInput, AgentRole
    from uuid import uuid4

    agent = ExecutorAgent()

    with patch("app.agents.executor.tool_registry") as mock_registry:
        mock_registry.list_tools = MagicMock(return_value=[
            {"name": "filesystem__read_file"},
            {"name": "filesystem__write_file"},
        ])

        input_data = AgentInput(
            task_id=uuid4(),
            step_id=uuid4(),
            role=AgentRole.EXECUTOR,
            input_data={
                "step": "read the report file",
                "tools": [],  # Empty tools_schema simulates the false-positive scenario
            },
        )

        result = await agent.execute(input_data)

    # Because filesystem tools ARE registered in the worker, the agent should NOT fail with tool_unavailable
    assert result.status != "failure" or result.error_type != "tool_unavailable", (
        f"Executor falsely reported filesystem tools unavailable. Error: {result.error_message}"
    )


@pytest.mark.asyncio
async def test_summarizer_handles_dict_outputs():
    from app.langgraph.nodes import summarizer_node
    from app.langgraph.state import AgentState
    from unittest.mock import AsyncMock, patch
    state = AgentState(
        task_id="test", user_id="u1", query="q",
        steps=[
            {"step_number": 1, "output": "text result"},
            {"step_number": 2, "output": {"message": "Browser already launched"}},
        ],
        messages=[], tool_calls=[], plan=[]
    )
    with patch("app.langgraph.nodes.get_llm_client") as mock_llm:
        mock_llm.return_value.complete_json = AsyncMock(return_value={"summary": "done"})
        result = await summarizer_node(state)
    assert result.get("status") == "completed"
    assert "done" in result["result"]["summary"]
