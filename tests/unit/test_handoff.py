"""Unit tests for agent handoff system: HandoffMessage, HandoffReceipt, InterAgentHandoff.

Tests match the actual API in app/agents/handoff.py.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from app.agents.handoff import (
    HandoffMessage,
    HandoffReceipt,
    HandoffReceiptSummary,
    InterAgentHandoff,
    get_handoff_manager,
)


class TestHandoffMessage:
    """Tests for HandoffMessage creation and validation."""

    def test_handoff_message_creation_with_all_fields(self):
        """HandoffMessage accepts all expected fields."""
        msg = HandoffMessage(
            from_agent="agent-a",
            to_agent="agent-b",
            task_id="task-123",
            state_snapshot={"key": "value"},
            context={"env": "test"},
            handoff_reason="task_delegation",
        )
        assert msg.from_agent == "agent-a"
        assert msg.to_agent == "agent-b"
        assert msg.task_id == "task-123"
        assert msg.state_snapshot == {"key": "value"}
        assert msg.context == {"env": "test"}
        assert msg.handoff_reason == "task_delegation"
        assert msg.signature is None

    def test_message_id_auto_generated_unique(self):
        """Each HandoffMessage gets a unique UUID string."""
        msg1 = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        msg2 = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        assert isinstance(msg1.message_id, str)
        assert len(msg1.message_id) == 36  # UUID format
        assert msg1.message_id != msg2.message_id

    def test_timestamp_auto_generated_iso_string(self):
        """Timestamp defaults to an ISO-format UTC string."""
        msg = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        assert isinstance(msg.timestamp, str)
        assert "T" in msg.timestamp  # ISO format contains T separator

    def test_validation_empty_from_agent_raises(self):
        """Empty from_agent raises ValueError."""
        with pytest.raises(ValueError, match="Agent IDs must be non-empty strings"):
            HandoffMessage(from_agent="", to_agent="agent-b", task_id="t1")

    def test_validation_empty_to_agent_raises(self):
        """Empty to_agent raises ValueError."""
        with pytest.raises(ValueError, match="Agent IDs must be non-empty strings"):
            HandoffMessage(from_agent="agent-a", to_agent="", task_id="t1")

    def test_whitespace_stripped_from_agent_ids(self):
        """Agent IDs are stripped of leading/trailing whitespace."""
        msg = HandoffMessage(
            from_agent="  agent-a  ",
            to_agent="  agent-b  ",
            task_id="t1",
        )
        assert msg.from_agent == "agent-a"
        assert msg.to_agent == "agent-b"

    def test_sign_produces_64_char_hex(self):
        """sign() produces a 64-character hex SHA-256 hash."""
        msg = HandoffMessage(
            from_agent="agent-a", to_agent="agent-b", task_id="t1",
            state_snapshot={"x": 1},
        )
        sig = msg.sign("test-secret")
        assert isinstance(sig, str)
        assert len(sig) == 64
        assert msg.signature == sig
        # Verify it's valid hex
        int(sig, 16)

    def test_verify_true_for_correct_secret(self):
        """verify() returns True when secret matches."""
        msg = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        msg.sign("correct-secret")
        assert msg.verify("correct-secret") is True

    def test_verify_false_for_wrong_secret(self):
        """verify() returns False when secret doesn't match."""
        msg = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        msg.sign("correct-secret")
        assert msg.verify("wrong-secret") is False

    def test_verify_detects_tampered_state_snapshot(self):
        """verify() fails if state_snapshot was modified after signing."""
        msg = HandoffMessage(
            from_agent="a", to_agent="b", task_id="t1",
            state_snapshot={"original": True},
        )
        msg.sign("secret")
        # Tamper with state
        msg.state_snapshot["tampered"] = True
        assert msg.verify("secret") is False

    def test_verify_detects_tampered_from_agent(self):
        """verify() fails if from_agent was modified after signing."""
        msg = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        msg.sign("secret")
        msg.from_agent = "tampered"
        assert msg.verify("secret") is False

    def test_verify_detects_tampered_to_agent(self):
        """verify() fails if to_agent was modified after signing."""
        msg = HandoffMessage(from_agent="a", to_agent="b", task_id="t1")
        msg.sign("secret")
        msg.to_agent = "tampered"
        assert msg.verify("secret") is False

    def test_same_data_same_signature(self):
        """Identical inputs produce identical signatures (deterministic)."""
        msg1 = HandoffMessage(
            from_agent="a", to_agent="b", task_id="t1",
            state_snapshot={"x": 1}, timestamp="2024-01-01T00:00:00",
        )
        msg2 = HandoffMessage(
            from_agent="a", to_agent="b", task_id="t1",
            state_snapshot={"x": 1}, timestamp="2024-01-01T00:00:00",
        )
        assert msg1.sign("s") == msg2.sign("s")

    def test_different_data_different_signature(self):
        """Different inputs produce different signatures."""
        msg1 = HandoffMessage(
            from_agent="a", to_agent="b", task_id="t1",
            state_snapshot={"x": 1}, timestamp="2024-01-01T00:00:00",
        )
        msg2 = HandoffMessage(
            from_agent="a", to_agent="b", task_id="t1",
            state_snapshot={"x": 2}, timestamp="2024-01-01T00:00:00",
        )
        assert msg1.sign("s") != msg2.sign("s")


class TestHandoffReceipt:
    """Tests for HandoffReceipt creation."""

    def test_receipt_creation_delivered_true(self):
        """HandoffReceipt with delivered=True sets all fields correctly."""
        receipt = HandoffReceipt(
            receipt_id="r-001",
            message_id="m-001",
            from_agent="agent-a",
            to_agent="agent-b",
            task_id="task-123",
            delivered=True,
            received_at="2024-01-01T12:00:00",
            processing_status="accepted",
        )
        assert receipt.delivered is True
        assert receipt.processing_status == "accepted"
        assert receipt.error_message is None

    def test_receipt_creation_delivered_false_with_error(self):
        """HandoffReceipt with delivered=False stores error_message."""
        receipt = HandoffReceipt(
            receipt_id="r-002",
            message_id="m-002",
            from_agent="agent-a",
            to_agent="agent-b",
            task_id="task-123",
            delivered=False,
            received_at="2024-01-01T12:00:00",
            processing_status="failed",
            error_message="Target agent not found",
        )
        assert receipt.delivered is False
        assert receipt.error_message == "Target agent not found"


class TestHandoffReceiptSummary:
    """Tests for HandoffReceiptSummary aggregation."""

    def test_summary_counts(self):
        """Summary correctly counts delivered vs failed receipts."""
        receipts = [
            HandoffReceipt(
                receipt_id=f"r-{i}", message_id=f"m-{i}",
                from_agent="a", to_agent="b", task_id="t1",
                delivered=(i % 2 == 0), received_at="2024-01-01T00:00:00",
            )
            for i in range(4)
        ]
        summary = HandoffReceiptSummary(
            task_id="t1",
            handoff_count=4,
            receipts=receipts,
            total_delivered=sum(1 for r in receipts if r.delivered),
            total_failed=sum(1 for r in receipts if not r.delivered),
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:01:00",
        )
        assert summary.total_delivered == 2
        assert summary.total_failed == 2
        assert summary.handoff_count == 4


class TestInterAgentHandoff:
    """Tests for InterAgentHandoff orchestration."""

    def setup_method(self):
        """Reset singleton and create fresh manager."""
        import app.agents.handoff as handoff_mod
        handoff_mod._handoff_instance = None
        self.manager = InterAgentHandoff(shared_secret="test-secret")

    @pytest.mark.asyncio
    async def test_handoff_success_with_mocked_runtime(self):
        """handoff() succeeds when runtime/worker are properly mocked."""
        mock_worker = MagicMock()
        mock_worker.inbox = asyncio.Queue()
        mock_runtime = MagicMock()
        mock_runtime.get.return_value = mock_worker

        with patch("app.runtime.runtime.AgentRuntime", return_value=mock_runtime):
            receipt = await self.manager.handoff(
                from_agent="agent-a",
                to_agent="agent-b",
                task_id="task-001",
                state_snapshot={"step": 1},
            )

        assert receipt.delivered is True
        assert receipt.from_agent == "agent-a"
        assert receipt.to_agent == "agent-b"
        assert receipt.task_id == "task-001"
        assert receipt.processing_status == "queued"

    @pytest.mark.asyncio
    async def test_handoff_failure_same_agent(self):
        """handoff() returns failure receipt when from_agent == to_agent."""
        receipt = await self.manager.handoff(
            from_agent="agent-a",
            to_agent="agent-a",
            task_id="task-001",
            state_snapshot={},
        )
        assert receipt.delivered is False
        assert "Cannot handoff to self" in receipt.error_message

    @pytest.mark.asyncio
    async def test_receive_handoff_verifies_signature(self):
        """receive_handoff() verifies signature and returns receipt."""
        msg = HandoffMessage(
            from_agent="agent-a", to_agent="agent-b", task_id="t1",
        )
        msg.sign("test-secret")

        receipt = await self.manager.receive_handoff(message=msg)
        assert receipt.delivered is True
        assert receipt.message_id == msg.message_id

    @pytest.mark.asyncio
    async def test_receive_handoff_with_worker_inbox(self):
        """receive_handoff() queues message into worker_inbox when provided."""
        msg = HandoffMessage(
            from_agent="agent-a", to_agent="agent-b", task_id="t1",
        )
        msg.sign("test-secret")

        inbox = asyncio.Queue()
        receipt = await self.manager.receive_handoff(
            message=msg, worker_inbox=inbox,
        )
        assert receipt.delivered is True
        assert not inbox.empty()
        queued = await inbox.get()
        assert queued.from_agent == "agent-a"

    @pytest.mark.asyncio
    async def test_batch_handoff_processes_multiple(self):
        """batch_handoff() processes list of handoff dicts."""
        mock_worker = MagicMock()
        mock_worker.inbox = asyncio.Queue()
        mock_runtime = MagicMock()
        mock_runtime.get.return_value = mock_worker

        handoffs = [
            {"from_agent": "a", "to_agent": "b", "task_id": "t1", "state_snapshot": {}},
            {"from_agent": "c", "to_agent": "d", "task_id": "t2", "state_snapshot": {}},
        ]

        with patch("app.runtime.runtime.AgentRuntime", return_value=mock_runtime):
            receipts = await self.manager.batch_handoff(handoffs)

        assert len(receipts) == 2
        assert all(r.delivered for r in receipts)

    def test_get_handoff_summary(self):
        """get_handoff_summary() returns summary for tracked task."""
        receipt = HandoffReceipt(
            receipt_id="r-1", message_id="m-1",
            from_agent="a", to_agent="b", task_id="task-123",
            delivered=True, received_at="2024-01-01T00:00:00",
        )
        self.manager._record_receipt("task-123", receipt)

        summary = self.manager.get_handoff_summary("task-123")
        assert summary is not None
        assert summary.task_id == "task-123"
        assert summary.total_delivered == 1

    def test_get_all_summaries(self):
        """get_all_summaries() returns dict of all tracked tasks."""
        self.manager._record_receipt("t1", HandoffReceipt(
            receipt_id="r-1", message_id="m-1",
            from_agent="a", to_agent="b", task_id="t1",
            delivered=True, received_at="2024-01-01T00:00:00",
        ))
        self.manager._record_receipt("t2", HandoffReceipt(
            receipt_id="r-2", message_id="m-2",
            from_agent="c", to_agent="d", task_id="t2",
            delivered=False, received_at="2024-01-01T00:00:00",
        ))

        all_summaries = self.manager.get_all_summaries()
        assert "t1" in all_summaries
        assert "t2" in all_summaries
        assert len(all_summaries) == 2


class TestGetHandoffManager:
    """Tests for module-level singleton."""

    def test_singleton_returns_same_instance(self, monkeypatch):
        """get_handoff_manager() returns the same instance on repeated calls."""
        import app.agents.handoff as handoff_mod
        monkeypatch.setattr(handoff_mod, "_handoff_instance", None)

        m1 = get_handoff_manager()
        m2 = get_handoff_manager()
        assert m1 is m2
        assert isinstance(m1, InterAgentHandoff)
