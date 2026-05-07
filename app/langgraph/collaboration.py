"""Collaboration orchestration for multi-agent execution in AgentOS.

Extends the compile_collaboration_graph() in graphs.py with:
- CollaborationSession tracking
- AgentGroup management
- SharedContext between collaborating agents
- GroupDecisionEngine (consensus, voting, priority)
- Message passing protocol between agents

Section 3.7: Collaboration Graph Compiler
"""
import json
import hashlib
import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..agents.base import AgentRole, AgentStatus


# ─── Enums ────────────────────────────────────────────────────────────────
class CollaborationStrategy(str, Enum):
    """How a group of agents makes decisions."""
    CONSENSUS = "consensus"       # All must agree
    MAJORITY = "majority"         # Simple majority vote
    PRIORITY = "priority"         # Highest-priority agent decides
    ROUND_ROBIN = "round_robin"   # Each agent contributes in turn
    DELEGATE = "delegate"         # Leader delegates to specialists


class MessageType(str, Enum):
    """Types of messages exchanged between collaborating agents."""
    TASK_ASSIGNMENT = "task_assignment"
    STATUS_UPDATE = "status_update"
    RESULT_SHARE = "result_share"
    QUESTION = "question"
    ANSWER = "answer"
    VOTE = "vote"
    CONSENSUS_REACHED = "consensus_reached"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


# ─── Pydantic Models ──────────────────────────────────────────────────────
class CollaborationConfig(BaseModel):
    """Configuration for a collaboration session."""
    session_id: str = Field(..., description="Unique session identifier")
    task_id: str = Field(..., description="Parent task identifier")
    strategy: CollaborationStrategy = Field(default=CollaborationStrategy.CONSENSUS)
    agents: List[str] = Field(default_factory=list, description="Agent IDs participating")
    leader_id: Optional[str] = Field(None, description="Designated leader agent ID")
    timeout_seconds: int = Field(default=300, description="Max session duration")
    quorum: int = Field(default=1, description="Minimum agents needed for quorum")
    allow_retry: bool = Field(default=True)


class CollaborationMessage(BaseModel):
    """Message passed between collaborating agents."""
    message_id: str = Field(default_factory=lambda: f"clmsg_{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:12]}")
    session_id: str
    from_agent: str
    to_agent: Optional[str] = None  # None = broadcast
    msg_type: MessageType
    content: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: Optional[str] = None  # Links request-response pairs
    sequence: int = 0
    requires_response: bool = False

    class Config:
        use_enum_values = True


class Vote(BaseModel):
    """A vote cast by an agent in a group decision."""
    agent_id: str
    choice: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GroupDecision(BaseModel):
    """Result of a group decision process."""
    topic: str
    strategy: CollaborationStrategy
    votes: List[Vote] = Field(default_factory=list)
    winner: Optional[str] = None
    consensus_reached: bool = False
    agreement_ratio: float = 0.0  # 0.0 to 1.0
    dissenting_agents: List[str] = Field(default_factory=list)
    resolved_at: Optional[str] = None
    notes: Optional[str] = None


# ─── Dataclasses ──────────────────────────────────────────────────────────
@dataclass
class AgentGroup:
    """A group of agents collaborating on a shared task."""
    group_id: str
    agent_ids: List[str]
    roles: Dict[str, AgentRole] = field(default_factory=dict)  # agent_id → role
    leader_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def has_quorum(self, min_agents: int = 1) -> bool:
        return len(self.agent_ids) >= min_agents


@dataclass
class SharedContext:
    """State shared between collaborating agents, with merge semantics."""
    data: Dict[str, Any] = field(default_factory=dict)
    version: int = 0
    last_updated_by: Optional[str] = None

    def merge(self, incoming: Dict[str, Any], agent_id: str) -> None:
        """Deep-merge incoming data, preserving existing keys not in incoming."""
        self._deep_merge(self.data, incoming)
        self.version += 1
        self.last_updated_by = agent_id

    @staticmethod
    def _deep_merge(base: Dict, incoming: Dict) -> None:
        for key, value in incoming.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                SharedContext._deep_merge(base[key], value)
            else:
                base[key] = value


@dataclass
class CollaborationSession:
    """Tracks state for an active collaboration session."""
    config: CollaborationConfig
    group: AgentGroup
    context: SharedContext = field(default_factory=SharedContext)
    messages: List[CollaborationMessage] = field(default_factory=list)
    decisions: List[GroupDecision] = field(default_factory=list)
    status: str = "initialized"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.status in ("initialized", "running")


# ─── GroupDecisionEngine ─────────────────────────────────────────────────
class GroupDecisionEngine:
    """Engine for group decision-making strategies (consensus, majority, priority)."""

    def __init__(self):
        self._pending_decisions: Dict[str, List[Vote]] = {}  # topic → votes

    def cast_vote(self, vote: Vote, topic: str) -> None:
        """Record a vote for a given topic."""
        if topic not in self._pending_decisions:
            self._pending_decisions[topic] = []
        # Replace existing vote from same agent
        self._pending_decisions[topic] = [
            v for v in self._pending_decisions[topic] if v.agent_id != vote.agent_id
        ]
        self._pending_decisions[topic].append(vote)
        logger.info(f"[GroupDecisionEngine] Vote cast: {vote.agent_id} → '{vote.choice}' for '{topic}'")

    def resolve(self, topic: str, strategy: CollaborationStrategy, quorum: int = 1) -> GroupDecision:
        """Resolve votes into a GroupDecision based on strategy."""
        votes = self._pending_decisions.get(topic, [])
        if len(votes) < quorum:
            return GroupDecision(
                topic=topic,
                strategy=strategy,
                votes=votes,
                consensus_reached=False,
                notes=f"Insufficient quorum: {len(votes)}/{quorum}",
            )

        if strategy == CollaborationStrategy.CONSENSUS:
            return self._resolve_consensus(topic, strategy, votes)
        elif strategy == CollaborationStrategy.MAJORITY:
            return self._resolve_majority(topic, strategy, votes)
        elif strategy == CollaborationStrategy.PRIORITY:
            return self._resolve_priority(topic, strategy, votes)
        elif strategy == CollaborationStrategy.ROUND_ROBIN:
            return self._resolve_round_robin(topic, strategy, votes)
        elif strategy == CollaborationStrategy.DELEGATE:
            return self._resolve_delegate(topic, strategy, votes)
        else:
            return GroupDecision(
                topic=topic, strategy=strategy, votes=votes,
                notes=f"Unknown strategy: {strategy}",
            )

    def _resolve_consensus(self, topic: str, strategy: CollaborationStrategy, votes: List[Vote]) -> GroupDecision:
        """All agents must agree on the same choice."""
        choices = set(v.choice for v in votes)
        if len(choices) == 1:
            return GroupDecision(
                topic=topic, strategy=strategy, votes=votes,
                winner=votes[0].choice, consensus_reached=True,
                agreement_ratio=1.0,
                resolved_at=datetime.now(timezone.utc).isoformat(),
            )
        return GroupDecision(
            topic=topic, strategy=strategy, votes=votes,
            consensus_reached=False, agreement_ratio=0.0,
            dissenting_agents=[v.agent_id for v in votes if v.choice != votes[0].choice],
            notes="Consensus not reached; agents disagreed.",
        )

    def _resolve_majority(self, topic: str, strategy: CollaborationStrategy, votes: List[Vote]) -> GroupDecision:
        """Simple majority (more than 50%) wins."""
        from collections import Counter
        tally = Counter(v.choice for v in votes)
        winner, count = tally.most_common(1)[0]
        majority_threshold = len(votes) / 2
        consensus = count > majority_threshold
        return GroupDecision(
            topic=topic, strategy=strategy, votes=votes,
            winner=winner, consensus_reached=consensus,
            agreement_ratio=count / len(votes) if votes else 0.0,
            dissenting_agents=[v.agent_id for v in votes if v.choice != winner],
            resolved_at=datetime.now(timezone.utc).isoformat() if consensus else None,
        )

    def _resolve_priority(self, topic: str, strategy: CollaborationStrategy, votes: List[Vote]) -> GroupDecision:
        """Highest-confidence vote wins."""
        sorted_votes = sorted(votes, key=lambda v: v.confidence, reverse=True)
        winner = sorted_votes[0]
        return GroupDecision(
            topic=topic, strategy=strategy, votes=votes,
            winner=winner.choice, consensus_reached=True,
            agreement_ratio=1.0,
            resolved_at=datetime.now(timezone.utc).isoformat(),
            notes=f"Priority decision: {winner.agent_id} (confidence: {winner.confidence})",
        )

    def _resolve_round_robin(self, topic: str, strategy: CollaborationStrategy, votes: List[Vote]) -> GroupDecision:
        """Each agent contributes in turn; last vote used as direction."""
        winner = votes[-1] if votes else None
        return GroupDecision(
            topic=topic, strategy=strategy, votes=votes,
            winner=winner.choice if winner else None,
            consensus_reached=True,
            agreement_ratio=1.0,
            resolved_at=datetime.now(timezone.utc).isoformat(),
            notes="Round-robin: last agent's vote accepted.",
        )

    def _resolve_delegate(self, topic: str, strategy: CollaborationStrategy, votes: List[Vote]) -> GroupDecision:
        """Delegate to leader (first agent in votes)."""
        leader = votes[0] if votes else None
        return GroupDecision(
            topic=topic, strategy=strategy, votes=votes,
            winner=leader.choice if leader else None,
            consensus_reached=True if leader else False,
            agreement_ratio=1.0 if leader else 0.0,
            resolved_at=datetime.now(timezone.utc).isoformat() if leader else None,
            notes="Delegated to leader.",
        )

    def clear_topic(self, topic: str) -> None:
        self._pending_decisions.pop(topic, None)


# ─── CollaborationOrchestrator ────────────────────────────────────────────
class CollaborationOrchestrator:
    """Orchestrates multi-agent collaboration sessions.

    Manages session lifecycle, message routing, shared context, and
    group decision-making for agent collaboration.
    """

    def __init__(self):
        self._sessions: Dict[str, CollaborationSession] = {}
        self._groups: Dict[str, AgentGroup] = {}
        self._message_queues: Dict[str, asyncio.Queue] = {}  # agent_id → inbox
        self._decision_engine = GroupDecisionEngine()

    # ── Session Management ──────────────────────────────────────────────
    def create_session(self, config: CollaborationConfig, group: AgentGroup) -> CollaborationSession:
        """Create and register a new collaboration session."""
        session = CollaborationSession(config=config, group=group, status="initialized")
        self._sessions[config.session_id] = session
        self._groups[group.group_id] = group
        logger.info(
            f"[CollaborationOrchestrator] Created session {config.session_id} "
            f"with {len(group.agent_ids)} agents, strategy={config.strategy.value}"
        )
        return session

    def get_session(self, session_id: str) -> Optional[CollaborationSession]:
        return self._sessions.get(session_id)

    def end_session(self, session_id: str) -> Optional[CollaborationSession]:
        session = self._sessions.pop(session_id, None)
        if session:
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"[CollaborationOrchestrator] Ended session {session_id}")
        return session

    # ── Message Passing ─────────────────────────────────────────────────
    def ensure_inbox(self, agent_id: str) -> None:
        if agent_id not in self._message_queues:
            self._message_queues[agent_id] = asyncio.Queue()

    async def send_message(self, msg: CollaborationMessage) -> bool:
        """Deliver a message to the target agent's inbox (or broadcast)."""
        session = self._sessions.get(msg.session_id)
        if not session:
            logger.warning(f"[CollaborationOrchestrator] Session {msg.session_id} not found")
            return False

        session.messages.append(msg)

        if msg.to_agent:
            # Direct message
            self.ensure_inbox(msg.to_agent)
            await self._message_queues[msg.to_agent].put(msg)
            logger.debug(f"[send_message] {msg.from_agent} → {msg.to_agent} [{msg.msg_type.value}]")
        else:
            # Broadcast to all agents in session except sender
            for agent_id in session.group.agent_ids:
                if agent_id == msg.from_agent:
                    continue
                self.ensure_inbox(agent_id)
                await self._message_queues[agent_id].put(msg)
            logger.debug(f"[send_message] {msg.from_agent} → broadcast [{msg.msg_type.value}]")
        return True

    async def receive_message(self, agent_id: str, timeout: float = 5.0) -> Optional[CollaborationMessage]:
        """Receive next message for an agent (non-blocking with timeout)."""
        if agent_id not in self._message_queues:
            return None
        try:
            return await asyncio.wait_for(
                self._message_queues[agent_id].get(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None

    # ── Shared Context ──────────────────────────────────────────────────
    def share_context(self, session_id: str, data: Dict[str, Any], agent_id: str) -> Optional[SharedContext]:
        """Update shared context with data from an agent."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        session.context.merge(data, agent_id)
        logger.debug(
            f"[share_context] Session {session_id}: agent {agent_id} "
            f"updated context (v{session.context.version})"
        )
        return session.context

    def get_shared_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        return session.context.data if session else None

    # ── Group Decision ──────────────────────────────────────────────────
    def cast_group_vote(self, session_id: str, agent_id: str, choice: str, confidence: float = 1.0, rationale: Optional[str] = None) -> bool:
        """Cast a vote in a group decision for the session."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        vote = Vote(agent_id=agent_id, choice=choice, confidence=confidence, rationale=rationale)
        self._decision_engine.cast_vote(vote, session_id)
        return True

    def resolve_group_decision(self, session_id: str) -> Optional[GroupDecision]:
        """Resolve pending votes for a session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        decision = self._decision_engine.resolve(
            topic=session_id,
            strategy=session.config.strategy,
            quorum=session.config.quorum,
        )
        if decision.consensus_reached:
            session.decisions.append(decision)
            self._decision_engine.clear_topic(session_id)
            logger.info(
                f"[CollaborationOrchestrator] Decision reached for {session_id}: "
                f"'{decision.winner}' (strategy={decision.strategy.value}, "
                f"agreement={decision.agreement_ratio:.0%})"
            )
        return decision

    # ── Group Management ────────────────────────────────────────────────
    def create_group(
        self,
        group_id: str,
        agent_ids: List[str],
        roles: Optional[Dict[str, AgentRole]] = None,
        leader_id: Optional[str] = None,
    ) -> AgentGroup:
        """Create an agent collaboration group."""
        group = AgentGroup(
            group_id=group_id,
            agent_ids=agent_ids,
            roles=roles or {},
            leader_id=leader_id,
        )
        self._groups[group_id] = group
        logger.info(f"[CollaborationOrchestrator] Created group {group_id}: {len(agent_ids)} agents")
        return group

    def get_group(self, group_id: str) -> Optional[AgentGroup]:
        return self._groups.get(group_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions with status."""
        return [
            {
                "session_id": s.config.session_id,
                "task_id": s.config.task_id,
                "status": s.status,
                "agent_count": len(s.group.agent_ids),
                "strategy": s.config.strategy.value,
                "message_count": len(s.messages),
                "started_at": s.started_at,
            }
            for s in self._sessions.values()
        ]


# ─── Singleton ────────────────────────────────────────────────────────────
_instance: Optional[CollaborationOrchestrator] = None


def get_collaboration_orchestrator() -> CollaborationOrchestrator:
    """Get or create the singleton CollaborationOrchestrator."""
    global _instance
    if _instance is None:
        _instance = CollaborationOrchestrator()
    return _instance


def reset_collaboration_orchestrator() -> None:
    """Reset the singleton (for testing)."""
    global _instance
    _instance = None
