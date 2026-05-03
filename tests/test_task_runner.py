"""Tests for TaskRunner — desktop recovery on verification failure."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.agents.base import AgentOutput, AgentStatus
from app.orchestrator.task_runner import TaskRunner
from app.capabilities.models import (
    Capability,
    CapabilityRequirement,
    CapabilityAssessment,
    FeasibilityResult,
    FeasibilityReport,
    ExecutionEnvironment,
    EnvironmentConfig,
    RecoveryAction,
    RecoveryDecision,
)


@pytest.mark.asyncio
async def test_task_runner_triggers_desktop_recovery_on_unverified():
    """FR3.3 + FR6: Desktop tasks should enter recovery, not fail immediately.
    
    When a LangGraph execution completes but verification returns False for a
    desktop task, TaskRunner should invoke recovery_engine.decide() and, if
    the decision is RETRY, re-run the task rather than returning FAILURE.
    """
    runner = TaskRunner()
    task_id = uuid4()

    # ── Model fixtures ──────────────────────────────────────────────
    assessment = CapabilityAssessment(
        task_id=str(task_id),
        query="open notepad",
        required_capabilities=[CapabilityRequirement(capability=Capability.DESKTOP)],
        primary_capability=Capability.DESKTOP,
        estimated_complexity=3,
    )
    feasibility = FeasibilityReport(
        task_id=str(task_id),
        result=FeasibilityResult.EXECUTABLE,
        available_capabilities=[Capability.DESKTOP],
        missing_capabilities=[],
        available_tools=["desktop_env__open_application"],
        missing_tools=[],
        environment_ready=True,
        safety_passed=True,
    )
    desktop_env = EnvironmentConfig(
        environment=ExecutionEnvironment.DESKTOP,
        working_dir="/tmp",
    )

    # ── Mock graph (verified=False → RETRY → verified=True) ─────────
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=[
        {"result": {}, "verified": False, "status": "completed"},
        {"result": {"notepad_opened": True}, "verified": True, "status": "completed"},
    ])

    # ── Mock recovery engine ────────────────────────────────────────
    mock_recovery = MagicMock()
    mock_recovery.decide = AsyncMock(return_value=RecoveryDecision(
        task_id=str(task_id),
        action=RecoveryAction.RETRY,
        reason="Desktop verification failed — retrying",
    ))

    with patch(
        "app.orchestrator.task_runner.recovery_engine", mock_recovery
    ), patch(
        "app.orchestrator.task_runner.capability_router"
    ) as mock_cap, patch(
        "app.orchestrator.task_runner.feasibility_engine"
    ) as mock_feas, patch(
        "app.orchestrator.task_runner.get_cached_graph", return_value=mock_graph
    ), patch(
        "app.orchestrator.task_runner.get_checkpointer"
    ), patch(
        "app.orchestrator.task_runner.execution_environment"
    ) as mock_exec_env, patch(
        "app.orchestrator.task_runner.event_bus"
    ) as mock_event_bus:

        mock_cap.classify = MagicMock(return_value=assessment)
        mock_feas.check = AsyncMock(return_value=feasibility)
        mock_feas.select_environment = MagicMock(return_value=desktop_env)
        mock_exec_env.configure = MagicMock()
        mock_exec_env.cleanup = MagicMock()
        mock_event_bus.publish = AsyncMock()

        result = await runner.run(
            query="open notepad",
            config={"mode": "autonomous"},
            task_id=task_id,
            user_id="test-user",
            mode="autonomous",
        )

    # ── Assertions ──────────────────────────────────────────────────
    assert result.status == AgentStatus.SUCCESS, (
        f"Expected SUCCESS after recovery retry, got {result.status}"
    )
    # Recovery engine must have been consulted
    mock_recovery.decide.assert_awaited_once()
    # Graph must have been invoked twice (first failed, second from retry)
    assert mock_graph.ainvoke.await_count == 2, (
        f"Expected 2 graph invocations (initial + retry), got {mock_graph.ainvoke.await_count}"
    )


@pytest.mark.asyncio
async def test_task_runner_returns_failure_when_recovery_does_not_retry():
    """Recovery decides a non-RETRY action → TaskRunner must return FAILURE."""
    runner = TaskRunner()
    task_id = uuid4()

    assessment = CapabilityAssessment(
        task_id=str(task_id),
        query="open notepad",
        required_capabilities=[CapabilityRequirement(capability=Capability.DESKTOP)],
        primary_capability=Capability.DESKTOP,
        estimated_complexity=3,
    )
    feasibility = FeasibilityReport(
        task_id=str(task_id),
        result=FeasibilityResult.EXECUTABLE,
        available_capabilities=[Capability.DESKTOP],
        missing_capabilities=[],
        available_tools=["desktop_env__open_application"],
        missing_tools=[],
        environment_ready=True,
        safety_passed=True,
    )
    desktop_env = EnvironmentConfig(
        environment=ExecutionEnvironment.DESKTOP,
        working_dir="/tmp",
    )

    # Graph returns unverified once — no second invocation expected
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={
        "result": {}, "verified": False, "status": "completed",
    })

    # Recovery engine returns ESCALATE (non-RETRY)
    mock_recovery = MagicMock()
    mock_recovery.decide = AsyncMock(return_value=RecoveryDecision(
        task_id=str(task_id),
        action=RecoveryAction.ESCALATE,
        reason="Unrecoverable — escalating to human",
    ))

    with patch(
        "app.orchestrator.task_runner.recovery_engine", mock_recovery
    ), patch(
        "app.orchestrator.task_runner.capability_router"
    ) as mock_cap, patch(
        "app.orchestrator.task_runner.feasibility_engine"
    ) as mock_feas, patch(
        "app.orchestrator.task_runner.get_cached_graph", return_value=mock_graph
    ), patch(
        "app.orchestrator.task_runner.get_checkpointer"
    ), patch(
        "app.orchestrator.task_runner.execution_environment"
    ) as mock_exec_env, patch(
        "app.orchestrator.task_runner.event_bus"
    ) as mock_event_bus:

        mock_cap.classify = MagicMock(return_value=assessment)
        mock_feas.check = AsyncMock(return_value=feasibility)
        mock_feas.select_environment = MagicMock(return_value=desktop_env)
        mock_exec_env.configure = MagicMock()
        mock_exec_env.cleanup = MagicMock()
        mock_event_bus.publish = AsyncMock()

        result = await runner.run(
            query="open notepad",
            config={"mode": "autonomous"},
            task_id=task_id,
            user_id="test-user",
            mode="autonomous",
        )

    assert result.status == AgentStatus.FAILURE, (
        f"Expected FAILURE when recovery does not retry, got {result.status}"
    )
    mock_recovery.decide.assert_awaited_once()
    # Graph invoked only once — no retry happened
    mock_graph.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_runner_respects_max_recovery_retries():
    """After MAX_RECOVERY_RETRIES (3) retry cycles, TaskRunner must return FAILURE."""
    runner = TaskRunner()
    task_id = uuid4()
    max_retries = runner.MAX_RECOVERY_RETRIES  # 3

    assessment = CapabilityAssessment(
        task_id=str(task_id),
        query="open notepad",
        required_capabilities=[CapabilityRequirement(capability=Capability.DESKTOP)],
        primary_capability=Capability.DESKTOP,
        estimated_complexity=3,
    )
    feasibility = FeasibilityReport(
        task_id=str(task_id),
        result=FeasibilityResult.EXECUTABLE,
        available_capabilities=[Capability.DESKTOP],
        missing_capabilities=[],
        available_tools=["desktop_env__open_application"],
        missing_tools=[],
        environment_ready=True,
        safety_passed=True,
    )
    desktop_env = EnvironmentConfig(
        environment=ExecutionEnvironment.DESKTOP,
        working_dir="/tmp",
    )

    # Graph always returns unverified — the underlying issue never resolves
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={
        "result": {}, "verified": False, "status": "completed",
    })

    # Recovery engine always returns RETRY
    mock_recovery = MagicMock()
    mock_recovery.decide = AsyncMock(return_value=RecoveryDecision(
        task_id=str(task_id),
        action=RecoveryAction.RETRY,
        reason="Transient error — retrying",
    ))

    with patch(
        "app.orchestrator.task_runner.recovery_engine", mock_recovery
    ), patch(
        "app.orchestrator.task_runner.capability_router"
    ) as mock_cap, patch(
        "app.orchestrator.task_runner.feasibility_engine"
    ) as mock_feas, patch(
        "app.orchestrator.task_runner.get_cached_graph", return_value=mock_graph
    ), patch(
        "app.orchestrator.task_runner.get_checkpointer"
    ), patch(
        "app.orchestrator.task_runner.execution_environment"
    ) as mock_exec_env, patch(
        "app.orchestrator.task_runner.event_bus"
    ) as mock_event_bus:

        mock_cap.classify = MagicMock(return_value=assessment)
        mock_feas.check = AsyncMock(return_value=feasibility)
        mock_feas.select_environment = MagicMock(return_value=desktop_env)
        mock_exec_env.configure = MagicMock()
        mock_exec_env.cleanup = MagicMock()
        mock_event_bus.publish = AsyncMock()

        result = await runner.run(
            query="open notepad",
            config={"mode": "autonomous"},
            task_id=task_id,
            user_id="test-user",
            mode="autonomous",
        )

    # Must return FAILURE after max retries
    assert result.status == AgentStatus.FAILURE, (
        f"Expected FAILURE after {max_retries} retries, got {result.status}"
    )
    assert result.error_type == "max_recovery_retries_exceeded", (
        f"Expected error_type 'max_recovery_retries_exceeded', got '{result.error_type}'"
    )
    # Recovery engine consulted max_retries times (before guard kicks in)
    expected_decide_calls = max_retries
    actual_decide_calls = mock_recovery.decide.await_count
    assert actual_decide_calls == expected_decide_calls, (
        f"Expected {expected_decide_calls} recovery.decide calls, got {actual_decide_calls}"
    )
    # Graph invoked max_retries + 1 times (initial + retries)
    expected_graph_calls = max_retries + 1
    actual_graph_calls = mock_graph.ainvoke.await_count
    assert actual_graph_calls == expected_graph_calls, (
        f"Expected {expected_graph_calls} graph invocations, got {actual_graph_calls}"
    )
