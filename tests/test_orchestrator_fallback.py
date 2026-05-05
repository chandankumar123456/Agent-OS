"""Phase 1 — Tests for orchestrator fallback chain.

Verifies:
- LangGraph execution is attempted first
- Checkpoint recovery is attempted on LangGraph failure
- Legacy ModeStrategyFactory is used as final fallback
- Unknown modes return FAILURE AgentOutput
- Fallback events are published to event bus
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.orchestrator.core import Orchestrator
from app.agents.base import AgentOutput, AgentStatus
from app.orchestrator.errors import UnrecoverableError, ErrorType


class TestOrchestratorFallbackChain:
    """Verify the orchestrator fallback chain: LangGraph → recovery → legacy → failure."""

    @pytest.fixture
    def orch(self):
        return Orchestrator()

    @pytest.mark.asyncio
    async def test_langgraph_executed_first(self, orch):
        """When LangGraph succeeds, should never reach legacy fallback."""
        success_result = AgentOutput(
            task_id=uuid4(),
            step_id=uuid4(),
            status=AgentStatus.SUCCESS,
            output_data={"result": "ok"},
        )

        with patch.object(
            orch, '_validate_input', new_callable=AsyncMock
        ) as mock_val:
            mock_val.return_value = None  # Pass input validation

            with patch.object(
                orch, '_execute_with_langgraph', new_callable=AsyncMock
            ) as mock_lg:
                mock_lg.return_value = success_result

                result = await orch.execute_task("test query", {"mode": "task"})

        assert result.status == AgentStatus.SUCCESS
        mock_lg.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_mode_returns_failure(self, orch):
        """When mode is not recognized, execute_task should return FAILURE."""
        task_id = uuid4()

        with patch.object(
            orch, '_validate_input', new_callable=AsyncMock
        ) as mock_val:
            mock_val.return_value = None

            with patch.object(
                orch, '_execute_with_langgraph', new_callable=AsyncMock
            ) as mock_lg:
                mock_lg.side_effect = RuntimeError("LangGraph failed")

                with patch(
                    'app.orchestrator.core.event_bus',
                ) as mock_bus:
                    mock_bus.publish = AsyncMock()

                    with patch(
                        'app.orchestrator.core.CheckpointRecoveryService',
                        new_callable=MagicMock
                    ) as mock_rec:
                        mock_rec.return_value.resume_task = AsyncMock(return_value=None)

                        with patch(
                            'app.orchestrator.core.ModeStrategyFactory',
                            new_callable=MagicMock
                        ) as mock_factory:
                            mock_factory.get.side_effect = ValueError("Unknown mode: invalid_mode")

                            result = await orch.execute_task(
                                "test", {"mode": "invalid_mode"}, task_id=task_id
                            )

        assert result.status == AgentStatus.FAILURE
        assert "invalid_mode" in result.error_message
        assert result.recoverable is False

    @pytest.mark.asyncio
    async def test_checkpoint_recovery_attempted_on_failure(self, orch):
        """When LangGraph fails, checkpoint recovery service should be called."""
        task_id = uuid4()

        with patch.object(
            orch, '_validate_input', new_callable=AsyncMock
        ) as mock_val:
            mock_val.return_value = None

            with patch.object(
                orch, '_execute_with_langgraph', new_callable=AsyncMock
            ) as mock_lg:
                # First call fails, second call (after recovery) succeeds
                mock_lg.side_effect = [
                    RuntimeError("first failure"),
                    AgentOutput(
                        task_id=task_id,
                        step_id=uuid4(),
                        status=AgentStatus.SUCCESS,
                        output_data={"recovered": True},
                    ),
                ]

                with patch(
                    'app.orchestrator.core.event_bus',
                ) as mock_bus:
                    mock_bus.publish = AsyncMock()

                    with patch(
                        'app.orchestrator.core.CheckpointRecoveryService',
                        new_callable=MagicMock
                    ) as mock_rec_cls:
                        mock_recovery = MagicMock()
                        mock_recovery.resume_task = AsyncMock(
                            return_value={"recovered": True}
                        )
                        mock_rec_cls.return_value = mock_recovery

                        result = await orch.execute_task(
                            "test", {"mode": "task"}, task_id=task_id
                        )

        assert result.status == AgentStatus.SUCCESS
        assert result.output_data.get("recovered") is True
        assert mock_recovery.resume_task.called
        assert mock_lg.call_count == 2  # Called twice: initial + after recovery

    @pytest.mark.asyncio
    async def test_fallback_event_published_on_langgraph_failure(self, orch):
        """When LangGraph fails, fallback event should be published to event_bus."""
        task_id = uuid4()

        with patch.object(
            orch, '_validate_input', new_callable=AsyncMock
        ) as mock_val:
            mock_val.return_value = None

            with patch.object(
                orch, '_execute_with_langgraph', new_callable=AsyncMock
            ) as mock_lg:
                mock_lg.side_effect = RuntimeError("LangGraph error")

                with patch(
                    'app.orchestrator.core.event_bus',
                ) as mock_bus:
                    mock_bus.publish = AsyncMock()

                    with patch(
                        'app.orchestrator.core.CheckpointRecoveryService',
                        new_callable=MagicMock
                    ) as mock_rec:
                        mock_rec.return_value.resume_task = AsyncMock(return_value=None)

                        with patch(
                            'app.orchestrator.core.ModeStrategyFactory',
                            new_callable=MagicMock
                        ) as mock_factory:
                            mock_strategy = MagicMock()
                            mock_strategy.execute = AsyncMock(return_value=AgentOutput(
                                task_id=task_id,
                                step_id=uuid4(),
                                status=AgentStatus.SUCCESS,
                                output_data={"fallback": True},
                            ))
                            mock_factory.get.return_value = mock_strategy

                            await orch.execute_task("test", {"mode": "task"}, task_id=task_id)

                    # Verify an event was published for this task
                    published_calls = [
                        call for call in mock_bus.publish.call_args_list
                        if f"task:{task_id}" in str(call.args)
                    ]
                    assert len(published_calls) > 0, "Expected a fallback event to be published"

    @pytest.mark.asyncio
    async def test_legacy_fallback_succeeds_when_langgraph_and_recovery_fail(self, orch):
        """Legacy mode strategies should be invoked when both LangGraph and recovery fail."""
        task_id = uuid4()

        with patch.object(
            orch, '_validate_input', new_callable=AsyncMock
        ) as mock_val:
            mock_val.return_value = None

            with patch.object(
                orch, '_execute_with_langgraph', new_callable=AsyncMock
            ) as mock_lg:
                mock_lg.side_effect = RuntimeError("LangGraph failed")

                with patch(
                    'app.orchestrator.core.event_bus',
                ) as mock_bus:
                    mock_bus.publish = AsyncMock()

                    with patch(
                        'app.orchestrator.core.CheckpointRecoveryService',
                        new_callable=MagicMock
                    ) as mock_rec:
                        mock_rec.return_value.resume_task = AsyncMock(return_value=None)

                        with patch(
                            'app.orchestrator.core.ModeStrategyFactory',
                            new_callable=MagicMock
                        ) as mock_factory:
                            mock_strategy = MagicMock()
                            mock_strategy.execute = AsyncMock(return_value=AgentOutput(
                                task_id=task_id,
                                step_id=uuid4(),
                                status=AgentStatus.SUCCESS,
                                output_data={"legacy_fallback": True},
                            ))
                            mock_factory.get.return_value = mock_strategy

                            result = await orch.execute_task(
                                "test", {"mode": "task"}, task_id=task_id
                            )

        assert result.status == AgentStatus.SUCCESS
        assert result.output_data.get("legacy_fallback") is True
        mock_factory.get.assert_called_once_with("task")

    @pytest.mark.asyncio
    async def test_input_guardrail_blocks_before_execution(self, orch):
        """When input validation fails, execution should NOT proceed to LangGraph."""
        with patch.object(
            orch, '_validate_input', new_callable=AsyncMock
        ) as mock_val:
            mock_val.side_effect = UnrecoverableError(
                "Input validation rejected",
                error_type=ErrorType.VALIDATION_ERROR,
            )

            with patch.object(
                orch, '_execute_with_langgraph', new_callable=AsyncMock
            ) as mock_lg:
                result = await orch.execute_task("bad query", {"mode": "task"})

        assert result.status == AgentStatus.FAILURE
        assert result.recoverable is False
        assert "Input validation rejected" in result.error_message
        mock_lg.assert_not_called()  # LangGraph should NOT be called
