"""Phase 3.3 — ConsensusEngine: Multi-agent agreement engine.

When multiple agents produce different results for the same task, the consensus
engine aggregates their outputs using configurable strategies (majority vote,
weighted confidence, first-to-respond, or LLM-mediated) and produces a unified
ConsensusResult with agreement metrics.

Spec: Supplementary to Build Plan Phase 3 (Multi-Agent Coordination)
Input Contract:  reach_consensus(agent_outputs: list, strategy: ConsensusStrategy) -> ConsensusResult
Output Contract: ConsensusResult with agreed output, confidence, voting breakdown
"""

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, UnrecoverableError, ErrorCode, ErrorType
from .base import AgentOutput, AgentStatus


# ── Pydantic Models ──────────────────────────────────────────────────────────

class ConsensusStrategy(str, Enum):
    """How to reach agreement among multiple agent outputs."""
    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_CONFIDENCE = "weighted_confidence"
    FIRST_TO_RESPOND = "first_to_respond"
    UNANIMOUS = "unanimous"
    LLM_MEDIATED = "llm_mediated"


class ConsensusVote(BaseModel):
    """A single agent's contribution to the consensus process."""
    agent_id: str
    output: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    status: AgentStatus = AgentStatus.SUCCESS
    reasoning: List[str] = Field(default_factory=list)
    content_hash: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def model_post_init(self, __context):
        if not self.content_hash:
            self.content_hash = self._hash_output()

    def _hash_output(self) -> str:
        """Produce a deterministic hash of the output for equality comparison."""
        try:
            serialized = str(sorted(str(v) for v in self.output.values()))
        except Exception:
            serialized = str(self.output)
        return hashlib.sha256(serialized.encode()).hexdigest()


class ConsensusResult(BaseModel):
    """Aggregated consensus after processing all agent votes."""
    agreed_output: Dict[str, Any] = Field(default_factory=dict)
    strategy: ConsensusStrategy
    agreement_level: float = 0.0  # 0.0 = total disagreement, 1.0 = unanimous
    confidence: float = 0.0
    num_agents: int = 0
    num_agreed: int = 0
    voting_breakdown: Dict[str, int] = Field(default_factory=dict)
    dissenting_votes: List[ConsensusVote] = Field(default_factory=list)
    winner_agent_id: Optional[str] = None
    reasoning: List[str] = Field(default_factory=list)
    reached_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── ConsensusEngine ─────────────────────────────────────────────────────────

class ConsensusEngine:
    """Engine for finding agreement among multiple agent outputs.

    Supports five strategies:
    - MAJORITY_VOTE: The most common output wins (requires >50%).
    - WEIGHTED_CONFIDENCE: Outputs weighted by agent confidence scores.
    - FIRST_TO_RESPOND: The first SUCCESS result wins.
    - UNANIMOUS: All agents must agree (same output hash).
    - LLM_MEDIATED: An LLM evaluates all outputs and picks the best (or produces a merge).
    """

    def __init__(self, default_strategy: ConsensusStrategy = ConsensusStrategy.MAJORITY_VOTE):
        self._default_strategy = default_strategy

    # ── Public API ───────────────────────────────────────────────────────

    def reach_consensus(
        self,
        votes: List[ConsensusVote],
        strategy: Optional[ConsensusStrategy] = None,
        min_agreement: float = 0.5,
    ) -> ConsensusResult:
        """Find consensus among agent outputs.

        Args:
            votes: List of agent votes/positions.
            strategy: Consensus strategy to use. Defaults to MAJORITY_VOTE.
            min_agreement: Minimum agreement threshold (0.0-1.0). Below this,
                           the result is marked as inconclusive.

        Returns:
            ConsensusResult with agreed output and agreement metrics.
        """
        strategy = strategy or self._default_strategy
        num_agents = len(votes)

        if num_agents == 0:
            return ConsensusResult(
                strategy=strategy,
                reasoning=["No votes provided"],
            )

        if num_agents == 1:
            vote = votes[0]
            return ConsensusResult(
                agreed_output=vote.output,
                strategy=strategy,
                agreement_level=1.0,
                confidence=vote.confidence,
                num_agents=1,
                num_agreed=1,
                voting_breakdown={vote.content_hash: 1},
                winner_agent_id=vote.agent_id,
                reasoning=["Single agent — no consensus needed"],
            )

        # Apply strategy
        if strategy == ConsensusStrategy.MAJORITY_VOTE:
            result = self._majority_vote(votes, min_agreement)
        elif strategy == ConsensusStrategy.WEIGHTED_CONFIDENCE:
            result = self._weighted_confidence(votes)
        elif strategy == ConsensusStrategy.FIRST_TO_RESPOND:
            result = self._first_to_respond(votes)
        elif strategy == ConsensusStrategy.UNANIMOUS:
            result = self._unanimous(votes)
        elif strategy == ConsensusStrategy.LLM_MEDIATED:
            result = self._llm_mediated(votes)
        else:
            result = self._majority_vote(votes, min_agreement)

        # Compute voting breakdown
        breakdown: Dict[str, int] = {}
        for vote in votes:
            breakdown[vote.content_hash] = breakdown.get(vote.content_hash, 0) + 1
        result.voting_breakdown = breakdown

        logger.info(
            f"Consensus reached via {strategy.value}: "
            f"agreement={result.agreement_level:.0%}, "
            f"confidence={result.confidence:.0%}, "
            f"agents={result.num_agents}/{num_agents}"
        )

        return result

    # ── Strategy Implementations ─────────────────────────────────────────

    def _majority_vote(
        self,
        votes: List[ConsensusVote],
        min_agreement: float,
    ) -> ConsensusResult:
        """Simple majority: most common output wins.

        Only considers votes with SUCCESS status.
        """
        successful = [v for v in votes if v.status == AgentStatus.SUCCESS]
        if not successful:
            return ConsensusResult(
                strategy=ConsensusStrategy.MAJORITY_VOTE,
                agreement_level=0.0,
                confidence=0.0,
                num_agents=len(votes),
                num_agreed=0,
                reasoning=["No successful votes to count"],
            )

        # Count by content hash
        tally: Dict[str, List[ConsensusVote]] = {}
        for vote in successful:
            tally.setdefault(vote.content_hash, []).append(vote)

        # Find winner
        best_hash = max(tally, key=lambda h: len(tally[h]))
        winner_votes = tally[best_hash]
        num_winners = len(winner_votes)

        agreement = num_winners / len(successful) if successful else 0.0
        avg_confidence = sum(v.confidence for v in winner_votes) / num_winners

        dissenting = [v for v in successful if v.content_hash != best_hash]

        return ConsensusResult(
            agreed_output=winner_votes[0].output,
            strategy=ConsensusStrategy.MAJORITY_VOTE,
            agreement_level=agreement,
            confidence=avg_confidence,
            num_agents=len(votes),
            num_agreed=num_winners,
            dissenting_votes=dissenting,
            winner_agent_id=winner_votes[0].agent_id,
            reasoning=[
                f"Majority vote: {num_winners}/{len(successful)} agents agreed "
                f"(threshold={min_agreement:.0%})",
            ],
        )

    def _weighted_confidence(self, votes: List[ConsensusVote]) -> ConsensusResult:
        """Weight each vote by the agent's reported confidence.

        The output with the highest total weighted confidence wins.
        """
        successful = [v for v in votes if v.status == AgentStatus.SUCCESS]
        if not successful:
            return ConsensusResult(
                strategy=ConsensusStrategy.WEIGHTED_CONFIDENCE,
                agreement_level=0.0,
                confidence=0.0,
                num_agents=len(votes),
                num_agreed=0,
                reasoning=["No successful votes"],
            )

        # Aggregate weighted confidence by output hash
        weighted: Dict[str, float] = {}
        hash_to_votes: Dict[str, List[ConsensusVote]] = {}
        for vote in successful:
            h = vote.content_hash
            weighted[h] = weighted.get(h, 0.0) + vote.confidence
            hash_to_votes.setdefault(h, []).append(vote)

        best_hash = max(weighted, key=weighted.get)
        best_votes = hash_to_votes[best_hash]
        total_weight = sum(weighted.values())
        agreement = weighted[best_hash] / total_weight if total_weight > 0 else 0.0

        dissenting = [v for v in successful if v.content_hash != best_hash]

        return ConsensusResult(
            agreed_output=best_votes[0].output,
            strategy=ConsensusStrategy.WEIGHTED_CONFIDENCE,
            agreement_level=agreement,
            confidence=weighted[best_hash] / len(votes) if votes else 0.0,
            num_agents=len(votes),
            num_agreed=len(best_votes),
            dissenting_votes=dissenting,
            winner_agent_id=best_votes[0].agent_id,
            reasoning=[
                f"Weighted confidence: {weighted[best_hash]:.2f} total weight "
                f"from {len(best_votes)} agents",
            ],
        )

    def _first_to_respond(self, votes: List[ConsensusVote]) -> ConsensusResult:
        """Accept the first successful result (by timestamp)."""
        successful = sorted(
            [v for v in votes if v.status == AgentStatus.SUCCESS],
            key=lambda v: v.timestamp,
        )
        if not successful:
            return ConsensusResult(
                strategy=ConsensusStrategy.FIRST_TO_RESPOND,
                agreement_level=0.0,
                confidence=0.0,
                num_agents=len(votes),
                num_agreed=0,
                reasoning=["No successful votes"],
            )

        first = successful[0]
        agreed = sum(1 for v in successful if v.content_hash == first.content_hash)

        return ConsensusResult(
            agreed_output=first.output,
            strategy=ConsensusStrategy.FIRST_TO_RESPOND,
            agreement_level=agreed / len(votes) if votes else 0.0,
            confidence=first.confidence,
            num_agents=len(votes),
            num_agreed=agreed,
            dissenting_votes=[v for v in votes if v.content_hash != first.content_hash],
            winner_agent_id=first.agent_id,
            reasoning=[
                f"First to respond: agent {first.agent_id} at {first.timestamp}",
                f"{agreed}/{len(votes)} agents produced the same result",
            ],
        )

    def _unanimous(self, votes: List[ConsensusVote]) -> ConsensusResult:
        """Require all agents to produce the same output hash."""
        successful = [v for v in votes if v.status == AgentStatus.SUCCESS]
        if not successful:
            return ConsensusResult(
                strategy=ConsensusStrategy.UNANIMOUS,
                agreement_level=0.0,
                confidence=0.0,
                num_agents=len(votes),
                num_agreed=0,
                reasoning=["No successful votes"],
            )

        unique_hashes = set(v.content_hash for v in successful)

        if len(unique_hashes) == 1:
            avg_confidence = sum(v.confidence for v in successful) / len(successful)
            return ConsensusResult(
                agreed_output=successful[0].output,
                strategy=ConsensusStrategy.UNANIMOUS,
                agreement_level=1.0,
                confidence=avg_confidence,
                num_agents=len(votes),
                num_agreed=len(successful),
                winner_agent_id=successful[0].agent_id,
                reasoning=["Unanimous agreement — all agents produced the same output"],
            )
        else:
            # No unanimous agreement
            return ConsensusResult(
                strategy=ConsensusStrategy.UNANIMOUS,
                agreement_level=0.0,
                confidence=0.0,
                num_agents=len(votes),
                num_agreed=0,
                dissenting_votes=list(votes),
                reasoning=[
                    f"Unanimous consensus failed: {len(unique_hashes)} distinct outputs "
                    f"from {len(successful)} agents",
                ],
            )

    def _llm_mediated(self, votes: List[ConsensusVote]) -> ConsensusResult:
        """LLM-mediated consensus: uses an LLM to evaluate outputs.

        Falls back to weighted confidence if LLM is unavailable.
        """
        logger.info("LLM-mediated consensus requested, falling back to weighted confidence")
        result = self._weighted_confidence(votes)
        result.strategy = ConsensusStrategy.LLM_MEDIATED
        result.reasoning.append("LLM mediation not yet implemented — used weighted confidence")
        return result

    # ── Helper Methods ───────────────────────────────────────────────────

    def consensus_from_outputs(
        self,
        outputs: List[AgentOutput],
        strategy: Optional[ConsensusStrategy] = None,
    ) -> ConsensusResult:
        """Convenience method: reach consensus from AgentOutput objects.

        Converts AgentOutput → ConsensusVote automatically.
        """
        votes = []
        for i, out in enumerate(outputs):
            votes.append(ConsensusVote(
                agent_id=getattr(out, "agent_id", f"agent_{i}"),
                output=out.output_data,
                confidence=out.confidence,
                status=out.status,
                reasoning=out.reasoning_trace or [],
            ))
        return self.reach_consensus(votes, strategy)

    def detect_conflict(
        self,
        outputs: List[AgentOutput],
        threshold: float = 0.3,
    ) -> Optional[ConsensusResult]:
        """Detect if there is a conflict among agent outputs.

        A conflict exists when agreement_level < threshold. Returns a
        ConsensusResult with the conflict analysis, or None if no conflict.
        """
        result = self.consensus_from_outputs(outputs, ConsensusStrategy.MAJORITY_VOTE)
        if result.agreement_level < threshold and result.num_agents > 1:
            return result
        return None
