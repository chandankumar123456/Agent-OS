"""Tests for ObservabilityBus."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.observability.bus import ObservabilityBus
from app.observability.models import ObservabilityEvent, ObservabilityEventType


@pytest.fixture
def bus():
    return ObservabilityBus()


@pytest.fixture
def sample_event():
    return ObservabilityEvent(
        event_type=ObservabilityEventType.TASK_RECEIVED,
        task_id="task-123",
        trace_id="trace-123",
        step_id="step-1",
        payload={"key": "value"},
        source="test",
    )


class TestEmit:
    @pytest.mark.asyncio
    async def test_logs_event(self, bus, sample_event):
        with patch("app.observability.bus.logger") as mock_logger:
            with patch(
                "app.orchestrator.event_bus.event_bus.publish", new=AsyncMock()
            ):
                with patch(
                    "app.memory.long_term.span_repo.create", new=AsyncMock()
                ):
                    await bus.emit(sample_event)

        mock_logger.info.assert_called_once()
        log_msg = mock_logger.info.call_args[0][0]
        assert "task.received" in log_msg
        assert "task-123" in log_msg
        assert "test" in log_msg

    @pytest.mark.asyncio
    async def test_publishes_to_event_bus(self, bus, sample_event):
        mock_publish = AsyncMock()
        with patch("app.orchestrator.event_bus.event_bus.publish", mock_publish):
            with patch("app.observability.bus.logger"):
                with patch(
                    "app.memory.long_term.span_repo.create", new=AsyncMock()
                ):
                    await bus.emit(sample_event)

        mock_publish.assert_awaited_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "task:task-123"
        event_arg = call_args[0][1]
        assert event_arg.event_type == "task.received"
        assert event_arg.payload["payload"] == {"key": "value"}
        assert event_arg.payload["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_persists_span(self, bus, sample_event):
        mock_create = AsyncMock()
        with patch("app.memory.long_term.span_repo.create", mock_create):
            with patch("app.observability.bus.logger"):
                with patch(
                    "app.orchestrator.event_bus.event_bus.publish", new=AsyncMock()
                ):
                    await bus.emit(sample_event)

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["trace_id"] == "trace-123"
        assert call_kwargs["span_id"].startswith("task.received:")
        assert call_kwargs["operation"] == "task.received"
        assert call_kwargs["agent_name"] == "test"
        assert call_kwargs["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_handles_event_bus_failure(self, bus, sample_event):
        mock_publish = AsyncMock(side_effect=Exception("redis down"))
        with patch("app.orchestrator.event_bus.event_bus.publish", mock_publish):
            with patch("app.observability.bus.logger") as mock_logger:
                with patch(
                    "app.memory.long_term.span_repo.create", new=AsyncMock()
                ):
                    await bus.emit(sample_event)

        mock_logger.warning.assert_called_once()
        assert "real-time publish failed" in mock_logger.warning.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_handles_span_repo_failure(self, bus, sample_event):
        mock_create = AsyncMock(side_effect=Exception("db down"))
        with patch("app.memory.long_term.span_repo.create", mock_create):
            with patch("app.observability.bus.logger") as mock_logger:
                with patch(
                    "app.orchestrator.event_bus.event_bus.publish", new=AsyncMock()
                ):
                    await bus.emit(sample_event)

        mock_logger.warning.assert_called_once()
        assert "db persist failed" in mock_logger.warning.call_args[0][0].lower()


class TestEmitSafe:
    @pytest.mark.asyncio
    async def test_builds_event_and_emits(self, bus):
        with patch.object(bus, "emit", new=AsyncMock()) as mock_emit:
            await bus.emit_safe(
                ObservabilityEventType.TOOL_INVOKED,
                task_id="task-456",
                trace_id="trace-456",
                step_id="step-2",
                payload={"tool": "shell"},
                source="executor",
            )

        mock_emit.assert_awaited_once()
        event = mock_emit.call_args[0][0]
        assert event.event_type == ObservabilityEventType.TOOL_INVOKED
        assert event.task_id == "task-456"
        assert event.trace_id == "trace-456"
        assert event.step_id == "step-2"
        assert event.payload == {"tool": "shell"}
        assert event.source == "executor"
        assert isinstance(event.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_swallows_errors(self, bus):
        with patch.object(
            bus, "emit", new=AsyncMock(side_effect=Exception("boom"))
        ) as mock_emit:
            with patch("app.observability.bus.logger") as mock_logger:
                await bus.emit_safe(
                    ObservabilityEventType.TASK_FAILED,
                    task_id="task-789",
                )

        mock_emit.assert_awaited_once()
        mock_logger.error.assert_called_once()
        assert "emit_safe failed" in mock_logger.error.call_args[0][0]
