"""Phase 3.1 — Inter-Agent Handoff Protocol: Structured state transfer between agents.

Enables agents to hand off work via structured state passing through AgentWorker
inbox queues. Not chat-based — uses typed HandoffMessage with integrity verification.

Spec: Build Plan Task 3.2.1, Section 6.3
Input Contract:  handoff(HandoffMessage) → HandoffReceipt
Output Contract: HandoffReceipt confirming delivery and receipt
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType

# ── Pydantic Models ──────────────────────────────────────────────────────────

class HandoffMessage(BaseModel):
    """Structured state transfer between agents during inter-agent handoff.

    Not chat-based. Transfers a subset of AgentState as a typed message
    with integrity verification via SHA-256 signature.
    """

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    from_agent: str = Field(..., description="Agent ID of the sending agent")
    to_agent: str = Field(..., description="Agent ID of the receiving agent")
    task_id: str = Field(..., description="Shared task identifier")
    state_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Subset of AgentState relevant to the handoff"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for the receiving agent"
    )
    handoff_reason: str = Field(
        default="task_delegation",
        description="Why the handoff is occurring (task_delegation, escalation, review, etc.)"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    signature: Optional[str] = Field(
        default=None,
        description="SHA-256 integrity signature (set by sign())"
    )

    @field_validator("from_agent", "to_agent", mode="before")
    @classmethod
    def validate_agent_ids(cls, v: Any) -> str:
        """Ensure agent IDs are non-empty strings."""
        if not v or not isinstance(v, str) or not v.strip():
            raise ValueError("Agent IDs must be non-empty strings")
        return v.strip()

    def sign(self, secret: str) -> str:
        """Compute and set the SHA-256 signature for integrity verification.

        Args:
            secret: A secret key shared between agents.

        Returns:
            The computed hex signature string.
        """
        payload = json.dumps(
            {
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "task_id": self.task_id,
                "state_snapshot": self.state_snapshot,
                "context": self.context,
                "handoff_reason": self.handoff_reason,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
            default=str,
        )
        self.signature = hashlib.sha256(
            f"{payload}:{secret}".encode("utf-8")
        ).hexdigest()
        return self.signature

    def verify(self, secret: str, expected_signature: Optional[str] = None) -> bool:
        """Verify the message integrity by recomputing the signature.

        Args:
            secret: The shared secret key.
            expected_signature: If provided, compare against this explicit value;
                                otherwise, compare against self.signature.

        Returns:
            True if the signature matches, False otherwise.
        """
        sig = expected_signature or self.signature
        if not sig:
            return False
        payload = json.dumps(
            {
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "task_id": self.task_id,
                "state_snapshot": self.state_snapshot,
                "context": self.context,
                "handoff_reason": self.handoff_reason,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
            default=str,
        )
        computed = hashlib.sha256(
            f"{payload}:{secret}".encode("utf-8")
        ).hexdigest()
        return computed == sig


class HandoffReceipt(BaseModel):
    """Confirmation that a handoff message was delivered and received."""

    receipt_id: str = Field(default_factory=lambda: str(uuid4()))
    message_id: str = Field(..., description="ID of the acknowledged HandoffMessage")
    from_agent: str
    to_agent: str
    task_id: str
    delivered: bool = True
    received_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    processing_status: Optional[str] = Field(
        default="queued",
        description="Current processing status (queued, processing, completed, failed)"
    )
    error_message: Optional[str] = None


class HandoffReceiptSummary(BaseModel):
    """Aggregated summary of handoff receipts for auditing."""

    task_id: str
    handoff_count: int = 0
    receipts: List[HandoffReceipt] = Field(default_factory=list)
    total_delivered: int = 0
    total_failed: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


# ── InterAgentHandoff ────────────────────────────────────────────────────────

class InterAgentHandoff:
    """Manages structured inter-agent handoffs via inbox-delivered messages.

    Flow:
    1. Sending agent creates a HandoffMessage with relevant state
    2. Message is validated against the HandoffMessage schema
    3. Message is delivered to the receiving agent's inbox queue (AgentWorker.inbox)
    4. Receiving agent processes the message and updates its state
    5. A HandoffReceipt is returned to the sender confirming delivery

    This is NOT chat-based. It is structured state passing.
    """

    def __init__(self, shared_secret: str = "agentos-handoff-v1"):
        self._shared_secret = shared_secret
        self._receipts: Dict[str, HandoffReceiptSummary] = {}

    # ── Public API ───────────────────────────────────────────────────────

    async def handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        state_snapshot: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        handoff_reason: str = "task_delegation",
    ) -> HandoffReceipt:
        """Initiate a handoff from one agent to another.

        Creates a signed HandoffMessage, delivers it to the receiving agent's
        inbox, and returns a HandoffReceipt confirming delivery.

        Args:
            from_agent: ID of the sending agent.
            to_agent: ID of the receiving agent.
            task_id: Shared task identifier.
            state_snapshot: Subset of AgentState to transfer.
            context: Additional context for the receiving agent.
            handoff_reason: Reason for the handoff.

        Returns:
            HandoffReceipt confirming delivery.

        Raises:
            AgentOSError: If the receiving agent rejects the handoff or delivery fails.
        """
        # Create and sign the message
        message = HandoffMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            task_id=task_id,
            state_snapshot=state_snapshot,
            context=context or {},
            handoff_reason=handoff_reason,
        )
        message.sign(self._shared_secret)

        logger.info(
            f"Handoff initiated: {from_agent} → {to_agent} "
            f"(task={task_id}, reason={handoff_reason})",
            extra={"task_id": task_id, "handoff_message_id": message.message_id},
        )

        # Validate the message before delivery
        try:
            self._validate_handoff_message(message)
        except ValueError as e:
            logger.error(f"Handoff validation failed: {e}")
            return HandoffReceipt(
                message_id=message.message_id,
                from_agent=from_agent,
                to_agent=to_agent,
                task_id=task_id,
                delivered=False,
                error_message=str(e),
            )

        # Deliver to receiving agent's inbox
        receipt = await self._deliver_to_agent(message)

        # Track for auditing
        self._record_receipt(task_id, receipt)

        logger.info(
            f"Handoff complete: {from_agent} → {to_agent} "
            f"(delivered={receipt.delivered}, receipt={receipt.receipt_id})",
            extra={"task_id": task_id, "receipt_id": receipt.receipt_id},
        )

        return receipt

    async def batch_handoff(
        self,
        handoffs: List[Dict[str, Any]],
    ) -> List[HandoffReceipt]:
        """Initiate multiple handoffs concurrently.

        Args:
            handoffs: List of dicts with keys: from_agent, to_agent, task_id,
                      state_snapshot, context (optional), handoff_reason (optional).

        Returns:
            List of HandoffReceipt results (one per handoff).
        """
        import asyncio

        tasks = []
        for h in handoffs:
            tasks.append(
                self.handoff(
                    from_agent=h["from_agent"],
                    to_agent=h["to_agent"],
                    task_id=h["task_id"],
                    state_snapshot=h.get("state_snapshot", {}),
                    context=h.get("context"),
                    handoff_reason=h.get("handoff_reason", "task_delegation"),
                )
            )

        return await asyncio.gather(*tasks, return_exceptions=False)

    async def receive_handoff(
        self,
        message: HandoffMessage,
        worker_inbox: Optional[Any] = None,
    ) -> HandoffReceipt:
        """Process a handoff received by an agent.

        Verifies signature integrity, validates the message, and optionally
        places it in the agent's inbox for processing.

        Args:
            message: The received HandoffMessage.
            worker_inbox: Optional asyncio.Queue inbox for the receiving agent.

        Returns:
            HandoffReceipt confirming receipt.
        """
        # Verify signature integrity
        if not message.verify(self._shared_secret):
            logger.error(
                f"Handoff signature verification failed for message {message.message_id}"
            )
            return HandoffReceipt(
                message_id=message.message_id,
                from_agent=message.from_agent,
                to_agent=message.to_agent,
                task_id=message.task_id,
                delivered=False,
                error_message="Signature verification failed",
            )

        # Validate message structure
        try:
            self._validate_handoff_message(message)
        except ValueError as e:
            return HandoffReceipt(
                message_id=message.message_id,
                from_agent=message.from_agent,
                to_agent=message.to_agent,
                task_id=message.task_id,
                delivered=False,
                error_message=str(e),
            )

        # Place in agent's inbox if available
        receipt = HandoffReceipt(
            message_id=message.message_id,
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            task_id=message.task_id,
            delivered=True,
            processing_status="queued",
        )

        if worker_inbox is not None:
            try:
                await worker_inbox.put(message)
                receipt.processing_status = "queued"
            except Exception as e:
                logger.error(
                    f"Failed to deliver handoff to inbox: {e}"
                )
                receipt.delivered = False
                receipt.error_message = f"Inbox delivery failed: {e}"
        else:
            receipt.processing_status = "received"
            receipt.error_message = "No inbox available; message not queued for processing"

        self._record_receipt(message.task_id, receipt)
        return receipt

    def get_handoff_summary(self, task_id: str) -> Optional[HandoffReceiptSummary]:
        """Get the handoff summary for a given task.

        Args:
            task_id: The task identifier.

        Returns:
            HandoffReceiptSummary if handoffs exist for this task, else None.
        """
        return self._receipts.get(task_id)

    def get_all_summaries(self) -> Dict[str, HandoffReceiptSummary]:
        """Get all handoff summaries across all tasks."""
        return dict(self._receipts)

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _validate_handoff_message(self, message: HandoffMessage) -> None:
        """Validate a handoff message before delivery.

        Args:
            message: The HandoffMessage to validate.

        Raises:
            ValueError: If the message fails validation.
        """
        if message.from_agent == message.to_agent:
            raise ValueError(
                f"Cannot handoff to self: {message.from_agent} → {message.to_agent}"
            )

        if not message.task_id:
            raise ValueError("task_id is required for handoff")

        if not message.from_agent.strip():
            raise ValueError("from_agent must be non-empty")

        if not message.to_agent.strip():
            raise ValueError("to_agent must be non-empty")

        # Warn on large state snapshots
        state_size = len(json.dumps(message.state_snapshot, default=str))
        if state_size > 1_000_000:  # 1MB
            logger.warning(
                f"Large state snapshot in handoff {message.message_id}: {state_size} bytes"
            )

    async def _deliver_to_agent(self, message: HandoffMessage) -> HandoffReceipt:
        """Deliver a handoff message to the receiving agent's inbox.

        Attempts to locate the AgentWorker for the target agent and deliver
        the message to its inbox queue.

        Args:
            message: The signed HandoffMessage to deliver.

        Returns:
            HandoffReceipt confirming delivery status.
        """
        receipt = HandoffReceipt(
            message_id=message.message_id,
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            task_id=message.task_id,
            delivered=False,
        )

        # Try to locate the receiving agent's worker
        try:
            from ..runtime.runtime import AgentRuntime

            runtime = AgentRuntime()
            worker = runtime.get(message.to_agent)

            if worker and hasattr(worker, "inbox") and worker.inbox is not None:
                await worker.inbox.put(message)
                receipt.delivered = True
                receipt.processing_status = "queued"
                logger.debug(
                    f"Handoff message {message.message_id} delivered to {message.to_agent} inbox"
                )
            else:
                # Agent not registered or no inbox — log and return unsuccessful
                logger.warning(
                    f"Handoff to {message.to_agent}: agent not found or no inbox available. "
                    f"Message {message.message_id} stored but not delivered to queue."
                )
                receipt.error_message = (
                    f"Agent '{message.to_agent}' not found or has no inbox queue"
                )
                receipt.processing_status = "pending"
        except Exception as e:
            logger.error(f"Handoff delivery to {message.to_agent} failed: {e}")
            receipt.error_message = f"Delivery error: {e}"
            receipt.processing_status = "failed"

        return receipt

    def _record_receipt(self, task_id: str, receipt: HandoffReceipt) -> None:
        """Record a handoff receipt for auditing.

        Args:
            task_id: The task identifier.
            receipt: The HandoffReceipt to record.
        """
        if task_id not in self._receipts:
            self._receipts[task_id] = HandoffReceiptSummary(
                task_id=task_id,
                started_at=datetime.now(timezone.utc).isoformat(),
            )

        summary = self._receipts[task_id]
        summary.receipts.append(receipt)
        summary.handoff_count = len(summary.receipts)
        summary.total_delivered = sum(1 for r in summary.receipts if r.delivered)
        summary.total_failed = sum(1 for r in summary.receipts if not r.delivered)
        summary.finished_at = datetime.now(timezone.utc).isoformat()


# ── Singleton ────────────────────────────────────────────────────────────────

_handoff_instance: Optional[InterAgentHandoff] = None


def get_handoff_manager(shared_secret: str = "agentos-handoff-v1") -> InterAgentHandoff:
    """Get or create the singleton InterAgentHandoff instance.

    Args:
        shared_secret: Secret key for message signing (only used on first call).

    Returns:
        The global InterAgentHandoff instance.
    """
    global _handoff_instance
    if _handoff_instance is None:
        _handoff_instance = InterAgentHandoff(shared_secret=shared_secret)
    return _handoff_instance
