"""Phase 3.2 — AgentRouter: Capability-based task routing.

Routes tasks to the most appropriate agent based on matching capabilities,
role requirements, tool access, and past performance. Integrates with the
orchestrator to replace simple mode-based routing with intelligent agent selection.

Spec: Build Plan Task 3.2.2 (Coordinator) + 3.2.6 (Multi-LLM Router)
Input Contract:  route(query: str, available_agents: list, context: dict) -> RoutingDecision
Output Contract: RoutingDecision with target agent, confidence, reasoning
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, UnrecoverableError, ErrorCode, ErrorType
from .base import AgentInput, AgentOutput, AgentRole


# ── Pydantic Models ──────────────────────────────────────────────────────────

class AgentCapability(BaseModel):
    """Describes an agent's capabilities for routing decisions."""
    agent_id: str
    role: AgentRole
    tools: List[str] = Field(default_factory=list)
    specialties: List[str] = Field(default_factory=list)
    success_rate: float = 0.8
    avg_latency_ms: float = 500.0
    max_concurrent: int = 1
    cost_per_task_usd: float = 0.0
    model: str = "gpt-4o"


class RoutingStrategy(str, Enum):
    """How to select an agent for a task."""
    CAPABILITY_MATCH = "capability_match"
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    LOWEST_COST = "lowest_cost"
    HIGHEST_SUCCESS_RATE = "highest_success_rate"
    ROLE_BASED = "role_based"


class RoutingDecision(BaseModel):
    """Result of the task routing decision."""
    task_id: Optional[str] = None
    target_agent_id: Optional[str] = None
    target_role: Optional[AgentRole] = None
    strategy: RoutingStrategy = RoutingStrategy.CAPABILITY_MATCH
    confidence: float = 0.0
    reasoning: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    estimated_cost_usd: float = 0.0
    estimated_latency_ms: float = 500.0
    fallback_agent_id: Optional[str] = None


class ComplexityScore(BaseModel):
    """Complexity analysis of a task query."""
    score: float = 0.5  # 0.0 = trivial, 1.0 = extremely complex
    num_steps_estimate: int = 1
    requires_planning: bool = False
    requires_verification: bool = False
    requires_approval: bool = False
    keywords_found: List[str] = Field(default_factory=list)
    capabilities_required: List[str] = Field(default_factory=list)
    reasoning: str = ""


# ── AgentRouter ─────────────────────────────────────────────────────────────

class AgentRouter:
    """Routes tasks to the most appropriate agent based on capabilities.

    Replaces simple mode-based routing with intelligent agent selection
    that considers agent capabilities, past performance, and task requirements.
    """

    name: str = "agent_router"

    def __init__(self, default_strategy: RoutingStrategy = RoutingStrategy.CAPABILITY_MATCH):
        self._default_strategy = default_strategy
        self._capabilities: Dict[str, AgentCapability] = {}
        self._round_robin_index: Dict[AgentRole, int] = {}

    # ── Public API ───────────────────────────────────────────────────────

    def register_agent(self, capability: AgentCapability) -> None:
        """Register an agent's capabilities for routing."""
        self._capabilities[capability.agent_id] = capability
        logger.info(
            f"Router registered agent {capability.agent_id} "
            f"(role={capability.role.value}, tools={len(capability.tools)})"
        )

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from routing consideration."""
        self._capabilities.pop(agent_id, None)
        logger.info(f"Router unregistered agent {agent_id}")

    def get_agents_by_role(self, role: AgentRole) -> List[AgentCapability]:
        """Get all registered agents matching a given role."""
        return [c for c in self._capabilities.values() if c.role == role]

    async def route(
        self,
        query: str,
        required_role: Optional[AgentRole] = None,
        required_tools: Optional[List[str]] = None,
        required_specialties: Optional[List[str]] = None,
        strategy: Optional[RoutingStrategy] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:
        """Route a task to the best available agent.

        Args:
            query: The task query or description.
            required_role: If set, only consider agents with this role.
            required_tools: If set, agents must have ALL these tools.
            required_specialties: If set, prefer agents with these specialties.
            strategy: Routing strategy override.
            context: Additional routing context (user preferences, task metadata).

        Returns:
            RoutingDecision with the chosen agent and confidence.
        """
        strategy = strategy or self._default_strategy
        context = context or {}

        # Score task complexity to inform routing
        complexity = self._score_complexity(query)

        # Filter candidates
        candidates = list(self._capabilities.values())
        if required_role:
            candidates = [c for c in candidates if c.role == required_role]
        if required_tools:
            candidates = [
                c for c in candidates
                if all(t in c.tools for t in required_tools)
            ]

        if not candidates:
            return RoutingDecision(
                confidence=0.0,
                reasoning=[f"No agents match role={required_role}, tools={required_tools}"],
                strategy=strategy,
            )

        # Select based on strategy
        if strategy == RoutingStrategy.ROLE_BASED:
            target = self._route_role_based(required_role or AgentRole.EXECUTOR)
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            target = self._route_round_robin(required_role or AgentRole.EXECUTOR)
        elif strategy == RoutingStrategy.LEAST_LOADED:
            target = self._route_least_loaded(candidates)
        elif strategy == RoutingStrategy.LOWEST_COST:
            target = self._route_lowest_cost(candidates)
        elif strategy == RoutingStrategy.HIGHEST_SUCCESS_RATE:
            target = self._route_highest_success_rate(candidates)
        else:
            # CAPABILITY_MATCH — score-based selection
            target = self._route_capability_match(
                candidates, query, required_specialties, complexity
            )

        if not target:
            return RoutingDecision(
                confidence=0.0,
                reasoning=["No agent matched after strategy filtering"],
                strategy=strategy,
            )

        # Build alternatives list
        alternatives = [
            c.agent_id for c in candidates
            if c.agent_id != target.agent_id
        ][:3]

        confidence = self._compute_confidence(target, complexity, candidates)

        return RoutingDecision(
            target_agent_id=target.agent_id,
            target_role=target.role,
            strategy=strategy,
            confidence=confidence,
            reasoning=[
                f"Matched agent {target.agent_id} ({target.role.value})",
                f"Complexity score: {complexity.score:.2f}",
                f"Strategy: {strategy.value}",
                f"Success rate: {target.success_rate:.0%}",
            ],
            alternatives=alternatives,
            estimated_cost_usd=target.cost_per_task_usd,
            estimated_latency_ms=target.avg_latency_ms,
            fallback_agent_id=alternatives[0] if alternatives else None,
        )

    def _score_complexity(self, query: str) -> ComplexityScore:
        """Score the complexity of a task query (0.0-1.0).

        Heuristic-based: counts keywords, steps, and patterns.
        """
        query_lower = query.lower()
        score = 0.0
        keywords: List[str] = []
        capabilities: List[str] = []

        # Multi-step indicators
        multi_step_words = [
            "first", "then", "after", "next", "finally", "also",
            "and then", "step 1", "step 2", "step one",
        ]
        steps_found = sum(1 for w in multi_step_words if w in query_lower)
        if steps_found:
            score += min(steps_found * 0.1, 0.3)
            keywords.extend(w for w in multi_step_words if w in query_lower)

        # Planning indicators — accumulate per keyword match
        planning_words = [
            "plan", "design", "architecture", "strategy", "analyze",
            "evaluate", "compare", "summarize",
        ]
        planning_hits = [w for w in planning_words if w in query_lower]
        if planning_hits:
            score += min(len(planning_hits) * 0.15, 0.4)
            keywords.extend(planning_hits)
            capabilities.append("planning")

        # Verification indicators
        verify_words = [
            "verify", "validate", "check", "confirm", "ensure",
            "test", "review", "audit",
        ]
        if any(w in query_lower for w in verify_words):
            score += 0.15
            keywords.extend(w for w in verify_words if w in query_lower)
            capabilities.append("verification")

        # Complex tool indicators
        tool_keywords = {
            "browse": "browser",
            "search": "search",
            "download": "filesystem",
            "upload": "filesystem",
            "create file": "filesystem",
            "desktop": "desktop",
            "notepad": "desktop",
            "chrome": "browser",
            "shell": "shell",
            "command": "shell",
        }
        for kw, cap in tool_keywords.items():
            if kw in query_lower:
                capabilities.append(cap)

        # Ambiguity / complexity
        if len(query.split()) > 50:
            score += 0.1
        if "?" in query:
            score += 0.05

        # Approximate step count
        num_steps = max(1, steps_found + 1)

        requires_planning = score >= 0.3
        requires_verification = "verification" in capabilities
        requires_approval = any(
            w in query_lower for w in ["delete", "remove", "payment", "approve"]
        )

        return ComplexityScore(
            score=min(score, 1.0),
            num_steps_estimate=num_steps,
            requires_planning=requires_planning,
            requires_verification=requires_verification,
            requires_approval=requires_approval,
            keywords_found=keywords,
            capabilities_required=capabilities,
            reasoning=f"Multi-step: {steps_found > 0}, Planning: {requires_planning}, "
                       f"Verification: {requires_verification}",
        )

    # ── Routing Strategies ───────────────────────────────────────────────

    def _route_capability_match(
        self,
        candidates: List[AgentCapability],
        query: str,
        specialties: Optional[List[str]],
        complexity: ComplexityScore,
    ) -> Optional[AgentCapability]:
        """Score-based capability match: higher is better."""
        if not candidates:
            return None

        query_lower = query.lower()
        scored: List[Tuple[float, AgentCapability]] = []

        for cap in candidates:
            score = 0.0
            # Tool match bonus
            tool_hits = sum(1 for t in cap.tools if t.lower().replace("_", " ") in query_lower)
            score += tool_hits * 0.1
            # Specialty match bonus
            if specialties:
                spec_hits = sum(1 for s in specialties if s in cap.specialties)
                score += spec_hits * 0.2
            # Success rate bonus
            score += cap.success_rate * 0.3
            # Penalty for high latency
            score -= min(cap.avg_latency_ms / 10000.0, 0.1)
            scored.append((score, cap))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _route_role_based(self, role: AgentRole) -> Optional[AgentCapability]:
        """Route based on exact role match."""
        candidates = self.get_agents_by_role(role)
        return candidates[0] if candidates else None

    def _route_round_robin(self, role: AgentRole) -> Optional[AgentCapability]:
        """Round-robin distribution across agents of the same role."""
        candidates = self.get_agents_by_role(role)
        if not candidates:
            return None
        idx = self._round_robin_index.get(role, 0)
        self._round_robin_index[role] = (idx + 1) % len(candidates)
        return candidates[idx]

    def _route_least_loaded(self, candidates: List[AgentCapability]) -> Optional[AgentCapability]:
        """Route to agent with most available capacity."""
        if not candidates:
            return None
        candidates.sort(key=lambda c: c.max_concurrent, reverse=True)
        return candidates[0]

    def _route_lowest_cost(self, candidates: List[AgentCapability]) -> Optional[AgentCapability]:
        """Route to cheapest agent."""
        if not candidates:
            return None
        candidates.sort(key=lambda c: c.cost_per_task_usd)
        return candidates[0]

    def _route_highest_success_rate(
        self, candidates: List[AgentCapability]
    ) -> Optional[AgentCapability]:
        """Route to agent with best track record."""
        if not candidates:
            return None
        candidates.sort(key=lambda c: c.success_rate, reverse=True)
        return candidates[0]

    def _compute_confidence(
        self,
        target: AgentCapability,
        complexity: ComplexityScore,
        candidates: List[AgentCapability],
    ) -> float:
        """Compute confidence in the routing decision (0.0-1.0)."""
        # More candidates = lower confidence in any single one
        diversity_penalty = max(0.0, (len(candidates) - 1) * 0.05)
        # Higher success rate = higher confidence
        success_factor = target.success_rate
        # Higher complexity = lower confidence
        complexity_factor = 1.0 - complexity.score * 0.3
        return max(0.1, min(0.99, success_factor * complexity_factor - diversity_penalty))
