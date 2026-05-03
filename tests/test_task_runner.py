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
