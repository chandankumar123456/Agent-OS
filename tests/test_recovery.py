import pytest
from unittest.mock import AsyncMock, patch
from core.capabilities.recovery import RecoveryEngine, RecoveryAction
from core.capabilities.models import VerificationReport, VerificationResult


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client for recovery tests."""
    client = AsyncMock()
    stored = {}

    async def _get(key):
        return stored.get(key)

    async def _incr(key):
        stored[key] = stored.get(key, 0) + 1
        return stored[key]

    async def _scan_iter(match):
        prefix = match.replace("*", "")
        for k in list(stored.keys()):
            if k.startswith(prefix):
                yield k

    client.get = AsyncMock(side_effect=_get)
    client.incr = AsyncMock(side_effect=_incr)
    client.expire = AsyncMock(return_value=True)
    client.scan_iter = _scan_iter
    client.delete = AsyncMock(return_value=0)
    with patch("core.capabilities.recovery.redis_client") as mock_rc:
        mock_rc.client = client
        yield client


@pytest.mark.asyncio
async def test_recovery_engine_retry_for_transient_error(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide("task-1", "step-1", error="Connection timeout")
    assert decision.action == RecoveryAction.RETRY
    assert "Transient" in decision.reason


@pytest.mark.asyncio
async def test_recovery_engine_escalate_after_max_retries(mock_redis):
    engine = RecoveryEngine(max_retries=2)
    # First two failures should retry
    d1 = await engine.decide("task-2", "step-1", error="Connection timeout")
    assert d1.action == RecoveryAction.RETRY
    d2 = await engine.decide("task-2", "step-1", error="Connection timeout")
    assert d2.action == RecoveryAction.RETRY
    # Third failure should escalate
    d3 = await engine.decide("task-2", "step-1", error="Connection timeout")
    assert d3.action == RecoveryAction.ESCALATE
    assert d3.max_retries_reached is True


@pytest.mark.asyncio
async def test_recovery_engine_replan_for_tool_not_found(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide("task-3", "step-1", error="tool not found")
    assert decision.action == RecoveryAction.REPLAN


@pytest.mark.asyncio
async def test_recovery_engine_escalate_for_permission_denied(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    decision = await engine.decide("task-4", "step-1", error="Permission denied")
    assert decision.action == RecoveryAction.ESCALATE


@pytest.mark.asyncio
async def test_recovery_engine_switch_tool_on_verification_fail(mock_redis):
    engine = RecoveryEngine(max_retries=3)
    v_report = VerificationReport(
        task_id="task-5",
        result=VerificationResult.FAIL,
        verifier_type="deterministic",
        retry_suggested=False,
    )
    decision = await engine.decide("task-5", "step-1", error="", verification_report=v_report, current_tool="filesystem__write_file")
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "shell__execute_command"


@pytest.mark.asyncio
async def test_recovery_engine_reset_retries(mock_redis):
    engine = RecoveryEngine(max_retries=2)
    await engine.decide("task-6", "step-1", error="Connection timeout")
    await engine.reset_retries("task-6")
    # After reset, should be able to retry again
    d = await engine.decide("task-6", "step-1", error="Connection timeout")
    assert d.action == RecoveryAction.RETRY


@pytest.mark.asyncio
async def test_checkpoint_recovery_service_resume_found():
    from core.recovery.checkpoint_service import CheckpointRecoveryService
    service = CheckpointRecoveryService()
    mock_checkpoint = {"channel_values": {"steps": ["step1"]}}
    mock_tuple = AsyncMock()
    mock_tuple.checkpoint = mock_checkpoint

    with patch("core.recovery.checkpoint_service.get_checkpointer") as mock_get_cp:
        mock_cp = AsyncMock()
        mock_cp.aget_tuple = AsyncMock(return_value=mock_tuple)
        mock_get_cp.return_value = mock_cp
        result = await service.resume_task("task-7", "task", {})
        assert result["steps"] == ["step1"]
        assert result["current_step_index"] == 0
        assert result["verified"] is False
        assert result["approved"] is None


@pytest.mark.asyncio
async def test_checkpoint_recovery_service_resume_not_found():
    from core.recovery.checkpoint_service import CheckpointRecoveryService
    service = CheckpointRecoveryService()
    with patch("core.recovery.checkpoint_service.get_checkpointer") as mock_get_cp:
        mock_cp = AsyncMock()
        mock_cp.aget_tuple = AsyncMock(return_value=None)
        mock_get_cp.return_value = mock_cp
        result = await service.resume_task("task-8", "task", {})
        assert result is None
