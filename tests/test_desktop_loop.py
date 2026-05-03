"""Failing tests for desktop goal-driven execution loop (TDD) and
verifier_node desktop verification.

These tests prove that AgentOS currently:
1. Does not check desktop goals via _check_desktop_goal
2. Stops prematurely after the first successful desktop tool call
3. Does not bound desktop loops with max_iterations
4. Returns SUCCESS even when verification fails
5. Does not catch missing desktop tool calls in verifier_node
6. Treats a single successful tool call as task success
7. (FR3.1 FIXED) verifier_node does not call verify_plan() for desktop

All tests are expected to FAIL until the implementation is written.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.langgraph.nodes import executor_node, verifier_node
from app.langgraph.state import AgentState
from app.orchestrator.task_runner import TaskRunner
from app.orchestrator.adaptive_routing import ExecutionTier, TaskRoutingDecision
from app.agents.base import AgentStatus


# ── Tests for executor_node desktop loop ──

@pytest.mark.asyncio
@patch("app.langgraph.nodes._check_desktop_goal", new_callable=AsyncMock, create=True)
@patch("app.langgraph.nodes.recovery_engine")
@patch("app.langgraph.nodes.verification_engine")
@patch("app.langgraph.nodes.tool_registry")
@patch("app.langgraph.nodes.get_llm_client")
@patch("app.langgraph.nodes.observability_bus")
async def test_desktop_loop_does_not_stop_after_first_action(
    mock_obs,
    mock_get_llm,
    mock_registry,
    mock_verification,
    mock_recovery,
    mock_check_goal,
):
    """Executor should call _check_desktop_goal after each iteration and
    continue making tool calls until the goal is actually achieved.
    """
    mock_obs.emit_safe = AsyncMock(return_value=None)

    # Goal is only achieved after the 3rd iteration
    mock_check_goal.side_effect = [(False, "not yet"), (False, "not yet"), (True, "done")]

    # LLM: tool call -> tool call -> direct answer
    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(side_effect=[
        {"tool_call": {"name": "desktop_env__press_key", "params": {"key": "win"}}},
        {"tool_call": {"name": "desktop_env__type_text", "params": {"text": "hello"}}},
        {"answer": "Task completed successfully", "details": "Notepad opened and text typed"},
    ])
    mock_get_llm.return_value = mock_llm

    mock_registry.list_tools = MagicMock(return_value=[
        {"name": "desktop_env__press_key", "description": "Press a key", "parameters": {"properties": {"key": {"type": "string"}}}},
        {"name": "desktop_env__type_text", "description": "Type text", "parameters": {"properties": {"text": {"type": "string"}}}},
    ])
    mock_registry.get = MagicMock(return_value=MagicMock())
    mock_tool_output = MagicMock()
    mock_tool_output.success = True
    mock_tool_output.result = "ok"
    mock_tool_output.error = None
    mock_registry.execute = AsyncMock(return_value=mock_tool_output)

    mock_verification.verify = AsyncMock(return_value=MagicMock(
        result=MagicMock(value="PASS"),
        model_dump=lambda: {},
    ))
    mock_recovery.decide = AsyncMock(return_value=MagicMock(
        action=MagicMock(value="retry"),
        reason="mock",
        next_tool=None,
        model_dump=lambda: {"action": "retry", "reason": "mock", "next_tool": None},
    ))

    state = AgentState(
        task_id="t1",
        user_id="u1",
        query="open notepad and type hello",
        plan=[{
            "step_number": 1,
            "description": "Open Notepad and type hello",
            "tool": "desktop_env__press_key",
            "allowed_tools": ["desktop_env__press_key", "desktop_env__type_text"],
            "fallback_tools": [],
            "expected_output": "Notepad is open with hello typed",
        }],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
        environment_config={"environment": "desktop"},
        max_tool_rounds=5,
    )

    result = await executor_node(state)

    # _check_desktop_goal should be invoked after each iteration to decide continuation
    assert mock_check_goal.call_count == 3, (
        f"Expected _check_desktop_goal to be called 3 times, got {mock_check_goal.call_count}"
    )
    # Two actual tool calls were made before the LLM provided an answer
    assert len(result["tool_calls"]) == 2, (
        f"Expected 2 tool calls, got {len(result['tool_calls'])}"
    )


@pytest.mark.asyncio
@patch("app.langgraph.nodes._check_desktop_goal", new_callable=AsyncMock, create=True)
@patch("app.langgraph.nodes.recovery_engine")
@patch("app.langgraph.nodes.verification_engine")
@patch("app.langgraph.nodes.tool_registry")
@patch("app.langgraph.nodes.get_llm_client")
@patch("app.langgraph.nodes.observability_bus")
async def test_goal_check_drives_continuation(
    mock_obs,
    mock_get_llm,
    mock_registry,
    mock_verification,
    mock_recovery,
    mock_check_goal,
):
    """_check_desktop_goal should determine when the loop stops.

    Even if the LLM keeps returning tool calls, the loop must stop
    exactly when the goal check returns True.
    """
    mock_obs.emit_safe = AsyncMock(return_value=None)

    # Goal not met on first 2 calls, met on 3rd
    mock_check_goal.side_effect = [(False, "not yet"), (False, "not yet"), (True, "done")]

    # LLM always returns a tool call (it never decides to stop on its own)
    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={
        "tool_call": {"name": "desktop_env__click", "params": {"x": 100, "y": 200}},
    })
    mock_get_llm.return_value = mock_llm

    mock_registry.list_tools = MagicMock(return_value=[
        {"name": "desktop_env__click", "description": "Click", "parameters": {"properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}},
    ])
    mock_registry.get = MagicMock(return_value=MagicMock())
    mock_tool_output = MagicMock()
    mock_tool_output.success = True
    mock_tool_output.result = "clicked"
    mock_tool_output.error = None
    mock_registry.execute = AsyncMock(return_value=mock_tool_output)

    mock_verification.verify = AsyncMock(return_value=MagicMock(
        result=MagicMock(value="PASS"),
        model_dump=lambda: {},
    ))
    mock_recovery.decide = AsyncMock(return_value=MagicMock(
        action=MagicMock(value="retry"),
        reason="mock",
        next_tool=None,
        model_dump=lambda: {"action": "retry", "reason": "mock", "next_tool": None},
    ))

    state = AgentState(
        task_id="t2",
        user_id="u1",
        query="click the save button",
        plan=[{
            "step_number": 1,
            "description": "Click the save button",
            "tool": "desktop_env__click",
            "allowed_tools": ["desktop_env__click"],
            "fallback_tools": [],
            "expected_output": "Button clicked",
        }],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
        environment_config={"environment": "desktop"},
        max_tool_rounds=5,
    )

    result = await executor_node(state)

    # Should stop after 3 iterations because goal is reached
    assert mock_check_goal.call_count == 3, (
        f"Expected 3 goal checks, got {mock_check_goal.call_count}"
    )
    assert len(result["tool_calls"]) == 3, (
        f"Expected 3 tool calls, got {len(result['tool_calls'])}"
    )


@pytest.mark.asyncio
@patch("app.langgraph.nodes._check_desktop_goal", new_callable=AsyncMock, create=True)
@patch("app.langgraph.nodes.recovery_engine")
@patch("app.langgraph.nodes.verification_engine")
@patch("app.langgraph.nodes.tool_registry")
@patch("app.langgraph.nodes.get_llm_client")
@patch("app.langgraph.nodes.observability_bus")
async def test_max_iterations_bounds_loop(
    mock_obs,
    mock_get_llm,
    mock_registry,
    mock_verification,
    mock_recovery,
    mock_check_goal,
):
    """If the desktop goal is never achieved, the loop must respect
    max_iterations and return an incomplete status.
    """
    mock_obs.emit_safe = AsyncMock(return_value=None)

    # Goal never met
    mock_check_goal.return_value = (False, "still not done")

    # LLM always wants to execute another tool
    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={
        "tool_call": {"name": "desktop_env__click", "params": {"x": 100, "y": 200}},
    })
    mock_get_llm.return_value = mock_llm

    mock_registry.list_tools = MagicMock(return_value=[
        {"name": "desktop_env__click", "description": "Click", "parameters": {"properties": {"x": {"type": "integer"}, "y": {"type": "integer"}}}},
    ])
    mock_registry.get = MagicMock(return_value=MagicMock())
    mock_tool_output = MagicMock()
    mock_tool_output.success = True
    mock_tool_output.result = "clicked"
    mock_tool_output.error = None
    mock_registry.execute = AsyncMock(return_value=mock_tool_output)

    mock_verification.verify = AsyncMock(return_value=MagicMock(
        result=MagicMock(value="PASS"),
        model_dump=lambda: {},
    ))
    mock_recovery.decide = AsyncMock(return_value=MagicMock(
        action=MagicMock(value="retry"),
        reason="mock",
        next_tool=None,
        model_dump=lambda: {"action": "retry", "reason": "mock", "next_tool": None},
    ))

    state = AgentState(
        task_id="t3",
        user_id="u1",
        query="click the save button",
        plan=[{
            "step_number": 1,
            "description": "Click the save button",
            "tool": "desktop_env__click",
            "allowed_tools": ["desktop_env__click"],
            "fallback_tools": [],
            "expected_output": "Button clicked",
        }],
        current_step_index=0,
        steps=[],
        tool_calls=[],
        messages=[],
        environment_config={"environment": "desktop"},
        max_tool_rounds=3,
    )

    result = await executor_node(state)

    # Should stop at 3 iterations
    assert mock_check_goal.call_count == 3, (
        f"Expected 3 goal checks, got {mock_check_goal.call_count}"
    )
    assert len(result["tool_calls"]) == 3, (
        f"Expected 3 tool calls, got {len(result['tool_calls'])}"
    )
    # Should indicate incomplete goal rather than pretending success
    assert result["status"] == "incomplete", (
        f"Expected status 'incomplete', got {result['status']}"
    )


# ── Tests for task_runner verification handling ──

@pytest.mark.asyncio
@patch("app.orchestrator.task_runner.event_bus")
@patch("app.orchestrator.task_runner.execution_environment")
@patch("app.orchestrator.task_runner.feasibility_engine")
@patch("app.orchestrator.task_runner.capability_router")
async def test_task_runner_returns_failure_when_not_verified(
    mock_capability,
    mock_feasibility,
    mock_execution_env,
    mock_event_bus,
):
    """TaskRunner must return AgentStatus.FAILURE when the graph
    finishes with verified=False, even if there is no error.
    """
    mock_event_bus.publish = AsyncMock(return_value=None)

    mock_capability.classify.return_value = MagicMock(
        primary_capability=MagicMock(value="desktop"),
        estimated_complexity=3,
        safety_flags=[],
        model_dump=lambda: {},
    )

    mock_feasibility.check = AsyncMock(return_value=MagicMock(
        result=MagicMock(value="PASS"),
        notes=[],
        model_dump=lambda: {},
    ))
    mock_feasibility.select_environment.return_value = MagicMock(
        environment=MagicMock(value="desktop"),
        working_dir="/tmp",
        model_dump=lambda: {},
    )

    mock_execution_env.configure = MagicMock()
    mock_execution_env.cleanup = MagicMock()

    with patch("app.orchestrator.task_runner.recovery_engine", None):
        with patch("app.orchestrator.task_runner.get_checkpointer", return_value=MagicMock()):
            with patch("app.orchestrator.task_runner.get_cached_graph") as mock_get_graph:
                mock_graph = AsyncMock()
                mock_graph.ainvoke = AsyncMock(return_value={
                    "verified": False,
                    "error": None,
                    "status": "completed",
                    "result": {},
                })
                mock_get_graph.return_value = mock_graph

                runner = TaskRunner()
                runner.task_complexity_router.classify = MagicMock(return_value=TaskRoutingDecision(
                    tier=ExecutionTier.FULL_RUNTIME,
                    reason="forced_tier2_for_test",
                    intents=(),
                ))
                result = await runner.run("open notepad", {}, uuid4(), "user-1", "autonomous")

                assert result.status == AgentStatus.FAILURE, (
                    f"Expected FAILURE when verified=False, got {result.status}"
                )


# ── Tests for verifier_node desktop awareness ──

@pytest.mark.asyncio
@patch("app.langgraph.nodes.get_llm_client")
@patch("app.langgraph.nodes.verification_engine")
@patch("app.langgraph.nodes.observability_bus")
async def test_verifier_node_catches_missing_desktop_calls(
    mock_obs,
    mock_verification_engine,
    mock_get_llm,
):
    """When the environment is 'desktop' but no desktop_env tools were
    invoked, verifier_node must set verified=False.
    """
    mock_obs.emit_safe = AsyncMock(return_value=None)

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={
        "verified": True,
        "notes": "LLM thinks it's fine",
    })
    mock_get_llm.return_value = mock_llm

    mock_verification_engine.verify_plan = AsyncMock(return_value=[])

    state = AgentState(
        task_id="t5",
        user_id="u1",
        query="open notepad",
        steps=[{
            "step_number": 1,
            "description": "Open Notepad",
            "output": "done",
            "tool_results": [],
        }],
        tool_calls=[],
        environment_config={"environment": "desktop"},
        plan=[{"step_number": 1, "description": "Open Notepad"}],
        messages=[],
    )

    result = await verifier_node(state)

    assert result["verified"] is False, (
        f"Expected verified=False for missing desktop calls, got {result['verified']}"
    )


# ── Integration-style test ──

@pytest.mark.asyncio
@patch("app.orchestrator.task_runner.event_bus")
@patch("app.orchestrator.task_runner.execution_environment")
@patch("app.orchestrator.task_runner.feasibility_engine")
@patch("app.orchestrator.task_runner.capability_router")
async def test_single_tool_success_does_not_equal_task_success(
    mock_capability,
    mock_feasibility,
    mock_execution_env,
    mock_event_bus,
):
    """A single successful desktop tool call must not result in SUCCESS
    if the verifier ultimately returns verified=False.
    """
    mock_event_bus.publish = AsyncMock(return_value=None)

    mock_capability.classify.return_value = MagicMock(
        primary_capability=MagicMock(value="desktop"),
        estimated_complexity=3,
        safety_flags=[],
        model_dump=lambda: {},
    )

    mock_feasibility.check = AsyncMock(return_value=MagicMock(
        result=MagicMock(value="PASS"),
        notes=[],
        model_dump=lambda: {},
    ))
    mock_feasibility.select_environment.return_value = MagicMock(
        environment=MagicMock(value="desktop"),
        working_dir="/tmp",
        model_dump=lambda: {},
    )

    mock_execution_env.configure = MagicMock()
    mock_execution_env.cleanup = MagicMock()

    with patch("app.orchestrator.task_runner.recovery_engine", None):
        with patch("app.orchestrator.task_runner.get_checkpointer", return_value=MagicMock()):
            with patch("app.orchestrator.task_runner.get_cached_graph") as mock_get_graph:
                mock_graph = AsyncMock()
                # Graph state: one desktop tool succeeded, but verifier said False
                mock_graph.ainvoke = AsyncMock(return_value={
                    "tool_calls": [
                        {"step": 1, "tool": "desktop_env__press_key", "result": {"success": True}},
                    ],
                    "steps": [{
                        "step_number": 1,
                        "description": "Open Notepad",
                        "output": "pressed key",
                        "tool_results": [{"success": True}],
                    }],
                    "verified": False,
                    "error": None,
                    "status": "completed",
                    "result": {},
                })
                mock_get_graph.return_value = mock_graph

                runner = TaskRunner()
                runner.task_complexity_router.classify = MagicMock(return_value=TaskRoutingDecision(
                    tier=ExecutionTier.FULL_RUNTIME,
                    reason="forced_tier2_for_test",
                    intents=(),
                ))
                result = await runner.run("open notepad", {}, uuid4(), "user-1", "autonomous")

                assert result.status != AgentStatus.SUCCESS, (
                    f"Expected status != SUCCESS for unverified task, got {result.status}"
                )
                assert result.status == AgentStatus.FAILURE, (
                    f"Expected FAILURE, got {result.status}"
                )


# ── FR3.1: verifier_node must call verify_plan() for desktop tasks ──

@pytest.mark.asyncio
@patch("app.langgraph.nodes.get_llm_client")
@patch("app.langgraph.nodes.verification_engine")
@patch("app.langgraph.nodes.observability_bus")
async def test_verifier_node_calls_verify_plan_for_desktop(
    mock_obs,
    mock_verification_engine,
    mock_get_llm,
):
    """FR3.1: verifier_node must call verification_engine.verify_plan()
    when env_type == 'desktop', running desktop-specific deterministic
    checks like desktop_app_opened and desktop_text_typed.
    """
    from app.capabilities.models import VerificationReport, VerificationResult

    mock_obs.emit_safe = AsyncMock(return_value=None)

    # Mock LLM verification as passing
    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={
        "verified": True,
        "notes": "LLM verification passed",
    })
    mock_get_llm.return_value = mock_llm

    # verify_plan returns desktop-specific reports
    mock_report = VerificationReport(
        task_id="desktop-verify-1",
        result=VerificationResult.PASS,
        verifier_type="deterministic",
        checks=[{"type": "desktop_app_opened"}],
        evidence={"app_name": "notepad"},
    )
    mock_verification_engine.verify_plan = AsyncMock(return_value=[mock_report])

    # State with desktop env and open_application success in tool_calls:
    # the top-level deterministic section skips verify_plan because of
    # the open_application match (line 1410), so the desktop block's
    # verify_plan call is the only one made and can be asserted.
    state = AgentState(
        task_id="desktop-verify-1",
        user_id="u1",
        query="open notepad and type hello",
        plan=[{"step_number": 1, "description": "Open Notepad"}],
        steps=[{"step_number": 1, "description": "Open Notepad", "output": "done"}],
        tool_calls=[
            {
                "step": 1,
                "tool": "desktop_env__open_application",
                "result": {"success": True, "data": {"pid": 1234, "window": "Notepad"}},
            }
        ],
        messages=[],
        environment_config={"environment": "desktop"},
    )

    result = await verifier_node(state)

    # verify_plan must have been called exactly once from the desktop block
    mock_verification_engine.verify_plan.assert_awaited_once()
    assert result["verified"] is True, (
        f"Expected verified=True, got {result['verified']}"
    )


# ── FR3.3: verifier_node returns False when desktop tools invoked but no state change ──

@pytest.mark.asyncio
@patch("app.langgraph.nodes.get_llm_client")
@patch("app.langgraph.nodes.verification_engine")
@patch("app.langgraph.nodes.observability_bus")
async def test_verifier_node_returns_false_when_desktop_tools_invoked_but_no_state_change(
    mock_obs,
    mock_verification_engine,
    mock_get_llm,
):
    """FR3.3: When desktop tools were invoked but verify_plan() returns
    zero reports (no matching verifiers found), verifier_node must set
    verified=False because state change could not be confirmed.
    """
    mock_obs.emit_safe = AsyncMock(return_value=None)

    # Mock LLM verification as passing
    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={
        "verified": True,
        "notes": "LLM verification passed",
    })
    mock_get_llm.return_value = mock_llm

    # verify_plan returns NO reports — no matching verifiers
    mock_verification_engine.verify_plan = AsyncMock(return_value=[])

    state = AgentState(
        task_id="fr33-test",
        user_id="u1",
        query="focus on notepad window",
        plan=[{"step_number": 1, "description": "Focus on Notepad"}],
        steps=[{"step_number": 1, "description": "Focus on Notepad", "output": "done"}],
        tool_calls=[
            {
                "step": 1,
                "tool": "desktop_env__press_key",
                "result": {"success": True},
            }
        ],
        messages=[],
        environment_config={"environment": "desktop"},
    )

    result = await verifier_node(state)

    # Desktop tools were invoked but verify_plan found no matching verifiers
    # → env_verified must be False → verified must be False
    assert result["verified"] is False, (
        f"Expected verified=False when desktop tools invoked but verify_plan returned no reports, got {result['verified']}"
    )
    assert "could not confirm state change" in result.get("verification_notes", ""), (
        f"Expected state change note in verification_notes, got: {result.get('verification_notes', '')}"
    )


# ── C1: _check_desktop_goal handles verify_plan exception gracefully ──

@pytest.mark.asyncio
@patch("app.langgraph.nodes.verification_engine")
async def test_check_desktop_goal_handles_verify_plan_exception(
    mock_verification_engine,
):
    """C1: _check_desktop_goal must catch exceptions from verify_plan()
    and return graceful fallback (False, error_msg) instead of crashing.
    """
    from app.langgraph.nodes import _check_desktop_goal

    # verify_plan raises an exception
    mock_verification_engine.verify_plan = AsyncMock(
        side_effect=RuntimeError("Desktop session not available")
    )

    reached, reason = await _check_desktop_goal(
        task_id="c1-test",
        step_description="click the cancel button",
        tool_calls=[
            {
                "step": 1,
                "tool": "desktop_env__click",
                "result": {"success": True},
            }
        ],
        step_number=1,
    )

    # Should return False with a graceful error message, not crash
    assert reached is False, (
        f"Expected goal_reached=False on exception, got {reached}"
    )
    assert "Verification fallback failed" in reason or "verify_plan" in reason.lower(), (
        f"Expected error message about verification fallback, got: {reason}"
    )


# ── Phase 3: LLM-driven _decide_action ──

@pytest.mark.asyncio
async def test_goal_loop_uses_llm_for_action_decision():
    """Phase 3: _decide_action must be LLM-driven, not hardcoded pattern matching."""
    from app.desktop.goal_loop import DesktopGoalLoop
    loop = DesktopGoalLoop(task_id="llm-test")
    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value={"tool": "desktop__click_element", "params": {"element_id": 5}})
    loop._llm = mock_llm

    action = await loop._decide_action(
        goal="Click the Submit button",
        desktop_state={"ui_tree": [{"id": 5, "name": "Submit", "type": "Button"}]},
        history=[],
    )
    assert action["tool"] == "desktop__click_element"
    mock_llm.complete_json.assert_awaited_once()


# ── Phase 3: executor_node delegates to DesktopGoalLoop ──

@pytest.mark.asyncio
async def test_executor_node_uses_desktop_goal_loop():
    """Phase 3: executor_node must delegate to DesktopGoalLoop for desktop tasks."""
    from app.langgraph.nodes import executor_node
    from app.langgraph.state import AgentState
    from unittest.mock import patch, AsyncMock, MagicMock

    mock_loop = AsyncMock()
    mock_loop.execute = AsyncMock(return_value={"status": "success", "actions": []})

    state = AgentState(
        messages=[],
        task_id="exec-desktop-1",
        plan=[{
            "step_number": 1,
            "description": "Open Notepad",
            "step_type": "desktop_automation",
            "tool": "desktop_env__open_application",
            "allowed_tools": [],
            "fallback_tools": [],
            "expected_output": "Notepad opened",
        }],
        current_step_index=0,
        environment_config={"environment": "desktop"},
    )

    with patch("app.langgraph.nodes.tool_registry") as mock_registry:
        mock_registry.list_tools = MagicMock(return_value=[])
        with patch("app.langgraph.nodes.observability_bus") as mock_obs:
            mock_obs.emit_safe = AsyncMock()
            with patch("app.langgraph.nodes.DesktopGoalLoop", return_value=mock_loop):
                result = await executor_node(state)

    mock_loop.execute.assert_awaited_once()
    assert result["status"] == "success"
