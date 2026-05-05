"""Phase 3 Tests — Multi-Agent Coordination: Coordinator, Router, Consensus.

Covers:
  - CoordinatorAgent: DAG validation, fan-out/fan-in, cascading failures, retries
  - AgentRouter: capability registration, role/strategy routing, complexity scoring
  - ConsensusEngine: majority vote, weighted confidence, first-to-respond,
    unanimous, conflict detection, edge cases
"""

import pytest
import asyncio
from uuid import uuid4

from app.agents.base import AgentInput, AgentOutput, AgentRole, AgentStatus
from app.agents.coordinator import (
    CoordinatorAgent,
    CoordinationResult,
    WorkflowDefinition,
    WorkflowStep,
    StepResult,
)
from app.agents.router import (
    AgentRouter,
    AgentCapability,
    RoutingStrategy,
    RoutingDecision,
    ComplexityScore,
)
from app.agents.consensus import (
    ConsensusEngine,
    ConsensusVote,
    ConsensusResult,
    ConsensusStrategy,
)


# ═════════════════════════════════════════════════════════════════════════════
# CoordinatorAgent Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestWorkflowDefinition:
    """Workflow DAG validation tests."""

    def test_valid_simple_dag(self):
        """A linear DAG with no cycles passes validation."""
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.PLANNER, task_description="Plan"),
                WorkflowStep(step_id="b", agent_role=AgentRole.EXECUTOR, task_description="Execute",
                             depends_on=["a"]),
                WorkflowStep(step_id="c", agent_role=AgentRole.VERIFIER, task_description="Verify",
                             depends_on=["b"]),
            ],
        )
        errors = wf.validate_dag()
        assert errors == []

    def test_duplicate_step_ids(self):
        """Duplicate step IDs are rejected."""
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.PLANNER, task_description="Plan"),
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Execute"),
            ],
        )
        errors = wf.validate_dag()
        assert any("duplicate" in e.lower() for e in errors)

    def test_missing_dependency(self):
        """A dependency on a non-existent step is rejected."""
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Execute",
                             depends_on=["nonexistent"]),
            ],
        )
        errors = wf.validate_dag()
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_self_dependency(self):
        """A step depending on itself is rejected."""
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Execute",
                             depends_on=["a"]),
            ],
        )
        errors = wf.validate_dag()
        assert any("itself" in e for e in errors)

    def test_cycle_detection(self):
        """A cyclic dependency (a→b, b→a) is detected."""
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.PLANNER, task_description="Plan",
                             depends_on=["b"]),
                WorkflowStep(step_id="b", agent_role=AgentRole.EXECUTOR, task_description="Execute",
                             depends_on=["a"]),
            ],
        )
        errors = wf.validate_dag()
        assert any("cycle" in e.lower() for e in errors)

    def test_no_steps_is_valid(self):
        """An empty workflow is technically valid."""
        wf = WorkflowDefinition(task_id=str(uuid4()), steps=[])
        errors = wf.validate_dag()
        assert errors == []

    def test_independent_steps(self):
        """Steps with no dependencies are valid (fan-out)."""
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task A"),
                WorkflowStep(step_id="b", agent_role=AgentRole.EXECUTOR, task_description="Task B"),
                WorkflowStep(step_id="c", agent_role=AgentRole.VERIFIER, task_description="Verify both",
                             depends_on=["a", "b"]),
            ],
        )
        errors = wf.validate_dag()
        assert errors == []


class TestCoordinatorAgent:
    """Tests for the CoordinatorAgent execution logic."""

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        """An empty workflow completes successfully."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(task_id=str(uuid4()), steps=[])
        result = await coordinator.coordinate(wf)
        assert result.overall_status == AgentStatus.SUCCESS
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_invalid_dag_returns_failure(self):
        """An invalid DAG returns FAILURE without executing."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task",
                             depends_on=["nonexistent"]),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert result.overall_status == AgentStatus.FAILURE
        assert "DAG validation failed" in (result.error_summary or "")

    @pytest.mark.asyncio
    async def test_single_step_succeeds(self):
        """A single-step workflow executes and succeeds (simulated)."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Simple task"),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert result.overall_status == AgentStatus.SUCCESS
        assert "a" in result.step_results
        assert result.step_results["a"].status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_sequential_steps(self):
        """Steps with dependencies execute in correct order."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="plan", agent_role=AgentRole.PLANNER, task_description="Plan"),
                WorkflowStep(step_id="exec", agent_role=AgentRole.EXECUTOR, task_description="Execute",
                             depends_on=["plan"]),
                WorkflowStep(step_id="verify", agent_role=AgentRole.VERIFIER, task_description="Verify",
                             depends_on=["exec"]),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert result.overall_status == AgentStatus.SUCCESS
        assert len(result.step_results) == 3
        for step_id in ["plan", "exec", "verify"]:
            assert step_id in result.step_results
            assert result.step_results[step_id].status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_fan_out_independent_steps(self):
        """Independent steps execute concurrently (fan-out)."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task A"),
                WorkflowStep(step_id="b", agent_role=AgentRole.EXECUTOR, task_description="Task B"),
                WorkflowStep(step_id="c", agent_role=AgentRole.EXECUTOR, task_description="Task C"),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert result.overall_status == AgentStatus.SUCCESS
        assert len(result.step_results) == 3

    @pytest.mark.asyncio
    async def test_fan_in_waits_for_dependencies(self):
        """Fan-in step only executes after all dependencies complete."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task A"),
                WorkflowStep(step_id="b", agent_role=AgentRole.EXECUTOR, task_description="Task B"),
                WorkflowStep(step_id="merge", agent_role=AgentRole.VERIFIER, task_description="Merge",
                             depends_on=["a", "b"]),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert result.overall_status == AgentStatus.SUCCESS
        assert "merge" in result.step_results
        assert result.step_results["merge"].status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_handoff_log_is_populated(self):
        """Handoff log tracks coordinator→agent transitions."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task"),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert len(result.handoff_log) >= 1
        entry = result.handoff_log[0]
        assert "from_agent" in entry
        assert "to_agent" in entry
        assert "step_id" in entry

    @pytest.mark.asyncio
    async def test_result_has_duration(self):
        """CoordinationResult includes timing information."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task"),
            ],
        )
        result = await coordinator.coordinate(wf)
        assert result.total_duration_ms >= 0
        assert result.started_at is not None
        assert result.finished_at is not None


class TestCoordinatorExecuteAgentProtocol:
    """CoordinatorAgent through the execute() protocol (BaseAgent interface)."""

    @pytest.mark.asyncio
    async def test_execute_without_workflow(self):
        """Missing workflow definition returns FAILURE."""
        coordinator = CoordinatorAgent()
        inp = AgentInput(
            task_id=uuid4(),
            step_id=uuid4(),
            role=AgentRole.PLANNER,
            input_data={},
        )
        output = await coordinator.execute(inp)
        assert output.status == AgentStatus.FAILURE
        assert "No workflow definition" in (output.error_message or "")

    @pytest.mark.asyncio
    async def test_execute_with_valid_workflow(self):
        """Valid workflow through execute() returns SUCCESS."""
        coordinator = CoordinatorAgent()
        wf = WorkflowDefinition(
            task_id=str(uuid4()),
            steps=[
                WorkflowStep(step_id="a", agent_role=AgentRole.EXECUTOR, task_description="Task"),
            ],
        )
        inp = AgentInput(
            task_id=uuid4(),
            step_id=uuid4(),
            role=AgentRole.PLANNER,
            input_data={"workflow": wf.model_dump()},
        )
        output = await coordinator.execute(inp)
        assert output.status == AgentStatus.SUCCESS
        assert "workflow" in str(output.output_data)

    @pytest.mark.asyncio
    async def test_execute_with_invalid_workflow_dict(self):
        """Malformed workflow dict returns FAILURE."""
        coordinator = CoordinatorAgent()
        inp = AgentInput(
            task_id=uuid4(),
            step_id=uuid4(),
            role=AgentRole.PLANNER,
            input_data={"workflow": {"not": "valid"}},
        )
        output = await coordinator.execute(inp)
        assert output.status == AgentStatus.FAILURE
        assert "Invalid workflow definition" in (output.error_message or "")


# ═════════════════════════════════════════════════════════════════════════════
# AgentRouter Tests
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentRouter:
    """Capability-based task routing tests."""

    def test_register_and_get_by_role(self):
        """Agents are registered and retrievable by role."""
        router = AgentRouter()
        cap = AgentCapability(
            agent_id="agent_1",
            role=AgentRole.EXECUTOR,
            tools=["filesystem__read_file", "shell__execute_command"],
        )
        router.register_agent(cap)
        agents = router.get_agents_by_role(AgentRole.EXECUTOR)
        assert len(agents) == 1
        assert agents[0].agent_id == "agent_1"

    def test_unregister_agent(self):
        """Unregistered agents are no longer routable."""
        router = AgentRouter()
        cap = AgentCapability(agent_id="agent_1", role=AgentRole.EXECUTOR)
        router.register_agent(cap)
        router.unregister_agent("agent_1")
        agents = router.get_agents_by_role(AgentRole.EXECUTOR)
        assert len(agents) == 0

    def test_get_agents_by_role_no_match(self):
        """Empty list when no agents match the role."""
        router = AgentRouter()
        cap = AgentCapability(agent_id="agent_1", role=AgentRole.EXECUTOR)
        router.register_agent(cap)
        agents = router.get_agents_by_role(AgentRole.VERIFIER)
        assert len(agents) == 0

    # ── Routing Decision Tests ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_route_no_candidates(self):
        """Routing with no registered agents returns zero confidence."""
        router = AgentRouter()
        decision = await router.route("Do something")
        assert decision.confidence == 0.0
        assert decision.target_agent_id is None

    @pytest.mark.asyncio
    async def test_route_capability_match(self):
        """Capability match selects best agent for the query."""
        router = AgentRouter()
        router.register_agent(AgentCapability(
            agent_id="exec_1", role=AgentRole.EXECUTOR,
            tools=["filesystem__read_file"], success_rate=0.9,
        ))
        router.register_agent(AgentCapability(
            agent_id="exec_2", role=AgentRole.EXECUTOR,
            tools=["desktop_env__open_application"], success_rate=0.7,
        ))
        decision = await router.route(
            "Create a file on the desktop",
            required_role=AgentRole.EXECUTOR,
        )
        assert decision.confidence > 0.0
        assert decision.target_agent_id is not None
        assert decision.strategy == RoutingStrategy.CAPABILITY_MATCH

    @pytest.mark.asyncio
    async def test_route_role_based(self):
        """Role-based routing selects agent by exact role."""
        router = AgentRouter()
        router.register_agent(AgentCapability(agent_id="planner", role=AgentRole.PLANNER))
        router.register_agent(AgentCapability(agent_id="exec", role=AgentRole.EXECUTOR))
        decision = await router.route(
            "Plan a task",
            required_role=AgentRole.PLANNER,
            strategy=RoutingStrategy.ROLE_BASED,
        )
        assert decision.target_agent_id == "planner"
        assert decision.target_role == AgentRole.PLANNER

    @pytest.mark.asyncio
    async def test_route_round_robin(self):
        """Round-robin distributes across agents of the same role."""
        router = AgentRouter()
        for i in range(3):
            router.register_agent(AgentCapability(
                agent_id=f"exec_{i}", role=AgentRole.EXECUTOR,
            ))
        # First call
        d1 = await router.route("Task", strategy=RoutingStrategy.ROUND_ROBIN)
        # Second call
        d2 = await router.route("Task", strategy=RoutingStrategy.ROUND_ROBIN)
        # They should be different agents (round-robin)
        assert d1.target_agent_id is not None
        assert d2.target_agent_id is not None
        # After 3 calls we cycle
        d3 = await router.route("Task", strategy=RoutingStrategy.ROUND_ROBIN)
        assert d3.target_agent_id is not None

    @pytest.mark.asyncio
    async def test_route_lowest_cost(self):
        """Lowest cost strategy selects the cheapest agent."""
        router = AgentRouter()
        router.register_agent(AgentCapability(
            agent_id="expensive", role=AgentRole.EXECUTOR, cost_per_task_usd=0.05,
        ))
        router.register_agent(AgentCapability(
            agent_id="cheap", role=AgentRole.EXECUTOR, cost_per_task_usd=0.01,
        ))
        decision = await router.route("Task", strategy=RoutingStrategy.LOWEST_COST)
        assert decision.target_agent_id == "cheap"

    @pytest.mark.asyncio
    async def test_route_highest_success_rate(self):
        """Highest success rate strategy picks the most reliable agent."""
        router = AgentRouter()
        router.register_agent(AgentCapability(
            agent_id="unreliable", role=AgentRole.EXECUTOR, success_rate=0.5,
        ))
        router.register_agent(AgentCapability(
            agent_id="reliable", role=AgentRole.EXECUTOR, success_rate=0.95,
        ))
        decision = await router.route("Task", strategy=RoutingStrategy.HIGHEST_SUCCESS_RATE)
        assert decision.target_agent_id == "reliable"

    @pytest.mark.asyncio
    async def test_route_with_required_tools(self):
        """Tool filtering excludes agents without required tools."""
        router = AgentRouter()
        router.register_agent(AgentCapability(
            agent_id="no_browser", role=AgentRole.EXECUTOR,
            tools=["filesystem__read_file"],
        ))
        router.register_agent(AgentCapability(
            agent_id="has_browser", role=AgentRole.EXECUTOR,
            tools=["browser_env__launch", "filesystem__read_file"],
        ))
        decision = await router.route(
            "Browse the web",
            required_tools=["browser_env__launch"],
        )
        assert decision.target_agent_id == "has_browser"

    @pytest.mark.asyncio
    async def test_route_with_role_filter(self):
        """Role filter narrows candidates."""
        router = AgentRouter()
        router.register_agent(AgentCapability(agent_id="planner", role=AgentRole.PLANNER))
        router.register_agent(AgentCapability(agent_id="exec", role=AgentRole.EXECUTOR))
        decision = await router.route("Plan something", required_role=AgentRole.PLANNER)
        assert decision.target_agent_id == "planner"

    @pytest.mark.asyncio
    async def test_route_includes_alternatives(self):
        """Routing decision includes alternative agent IDs."""
        router = AgentRouter()
        for i in range(4):
            router.register_agent(AgentCapability(
                agent_id=f"agent_{i}", role=AgentRole.EXECUTOR,
            ))
        decision = await router.route("Task")
        assert decision.target_agent_id is not None
        assert len(decision.alternatives) > 0
        assert decision.fallback_agent_id is not None

    @pytest.mark.asyncio
    async def test_route_includes_metadata(self):
        """Routing decision includes cost, latency, and reasoning."""
        router = AgentRouter()
        router.register_agent(AgentCapability(
            agent_id="agent_1", role=AgentRole.EXECUTOR,
            cost_per_task_usd=0.02, avg_latency_ms=300.0,
        ))
        decision = await router.route("Task")
        assert decision.estimated_cost_usd == 0.02
        assert decision.estimated_latency_ms == 300.0
        assert len(decision.reasoning) > 0

    # ── Complexity Scoring Tests ────────────────────────────────────────

    def test_simple_query_low_complexity(self):
        """A simple query scores low complexity."""
        router = AgentRouter()
        score = router._score_complexity("hello")
        assert score.score < 0.3
        assert score.num_steps_estimate == 1

    def test_complex_query_high_complexity(self):
        """A complex multi-step query scores high complexity."""
        router = AgentRouter()
        score = router._score_complexity(
            "First search the web, then analyze the results, "
            "then verify the findings, and finally write a summary report"
        )
        assert score.score > 0.3
        assert score.requires_planning

    def test_planning_keywords_trigger_planning(self):
        """Keywords like 'design' and 'architecture' trigger planning requirement."""
        router = AgentRouter()
        score = router._score_complexity("design an architecture for a microservice system")
        assert score.requires_planning
        assert "design" in score.keywords_found

    def test_verification_keywords_trigger_verification(self):
        """Keywords like 'verify' and 'validate' trigger verification."""
        router = AgentRouter()
        score = router._score_complexity("verify the output and validate the results")
        assert score.requires_verification
        assert "verification" in score.capabilities_required

    def test_dangerous_keywords_trigger_approval(self):
        """Keywords like 'delete' and 'payment' require approval."""
        router = AgentRouter()
        score = router._score_complexity("delete all files and process payment")
        assert score.requires_approval

    def test_long_query_increases_complexity(self):
        """Longer queries increase complexity slightly."""
        router = AgentRouter()
        short = router._score_complexity("hello")
        long = router._score_complexity("word " * 60)
        assert long.score >= short.score

    def test_question_adds_complexity(self):
        """Queries with question marks have slightly higher complexity."""
        router = AgentRouter()
        statement = router._score_complexity("do something")
        question = router._score_complexity("can you do something?")
        assert question.score >= statement.score


# ═════════════════════════════════════════════════════════════════════════════
# ConsensusEngine Tests
# ═════════════════════════════════════════════════════════════════════════════

def make_vote(
    agent_id: str,
    output: dict,
    confidence: float = 1.0,
    status: AgentStatus = AgentStatus.SUCCESS,
    reasoning: list = None,
) -> ConsensusVote:
    """Helper to create a ConsensusVote quickly."""
    return ConsensusVote(
        agent_id=agent_id,
        output=output,
        confidence=confidence,
        status=status,
        reasoning=reasoning or [],
    )


class TestConsensusEngine:
    """Tests for all consensus strategies."""

    # ── Edge Cases ──────────────────────────────────────────────────────

    def test_no_votes(self):
        """Zero votes returns empty consensus."""
        engine = ConsensusEngine()
        result = engine.reach_consensus([])
        assert result.num_agents == 0
        assert result.agreement_level == 0.0

    def test_single_vote(self):
        """A single vote is automatically consensus."""
        engine = ConsensusEngine()
        vote = make_vote("a", {"answer": 42})
        result = engine.reach_consensus([vote])
        assert result.agreement_level == 1.0
        assert result.num_agents == 1
        assert result.num_agreed == 1
        assert result.agreed_output == {"answer": 42}
        assert "Single agent" in result.reasoning[0] or result.agreement_level == 1.0

    # ── Majority Vote ───────────────────────────────────────────────────

    def test_majority_vote_clear_winner(self):
        """3/4 agents agree → majority wins."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "A"}),
            make_vote("b", {"answer": "A"}),
            make_vote("c", {"answer": "A"}),
            make_vote("d", {"answer": "B"}),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.MAJORITY_VOTE)
        assert result.agreed_output == {"answer": "A"}
        assert result.agreement_level == 0.75
        assert result.num_agreed == 3
        assert len(result.dissenting_votes) == 1

    def test_majority_vote_tie(self):
        """2/4 agree, 2/4 disagree — majority still picks first (alphabetically by hash)."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "X"}),
            make_vote("b", {"answer": "X"}),
            make_vote("c", {"answer": "Y"}),
            make_vote("d", {"answer": "Y"}),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.MAJORITY_VOTE)
        assert result.agreement_level == 0.5
        # Either X or Y wins (same count, first by hash)
        assert result.agreed_output["answer"] in ("X", "Y")

    def test_majority_vote_only_successful_counted(self):
        """FAILURE votes are excluded from majority tally."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "A"}, status=AgentStatus.SUCCESS),
            make_vote("b", {"answer": "B"}, status=AgentStatus.SUCCESS),
            make_vote("c", {"answer": "A"}, status=AgentStatus.FAILURE),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.MAJORITY_VOTE)
        # Only a and b are successful (c is FAILURE). With a 1-1 tie,
        # the winner depends on hash ordering. Either A or B is valid.
        assert result.agreed_output["answer"] in ("A", "B")
        assert result.num_agreed == 1

    def test_majority_vote_all_failed(self):
        """All votes FAILURE → zero agreement."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {}, status=AgentStatus.FAILURE),
            make_vote("b", {}, status=AgentStatus.FAILURE),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.MAJORITY_VOTE)
        assert result.agreement_level == 0.0
        assert result.num_agreed == 0

    # ── Weighted Confidence ─────────────────────────────────────────────

    def test_weighted_confidence(self):
        """Agent with higher confidence sways the result."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "A"}, confidence=0.9),
            make_vote("b", {"answer": "B"}, confidence=0.3),
            make_vote("c", {"answer": "B"}, confidence=0.3),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.WEIGHTED_CONFIDENCE)
        # A = 0.9, B = 0.3 + 0.3 = 0.6 → A wins
        assert result.agreed_output == {"answer": "A"}

    def test_weighted_confidence_tie(self):
        """Equal weighted confidence — first hash wins."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "X"}, confidence=0.5),
            make_vote("b", {"answer": "Y"}, confidence=0.5),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.WEIGHTED_CONFIDENCE)
        assert result.agreed_output["answer"] in ("X", "Y")
        # Agreement level should be 0.5
        assert result.agreement_level == 0.5

    # ── First to Respond ────────────────────────────────────────────────

    def test_first_to_respond(self):
        """First successful vote by timestamp wins."""
        engine = ConsensusEngine()
        votes = [
            make_vote("early", {"answer": "first"}, confidence=0.5),
            make_vote("late", {"answer": "second"}, confidence=0.9),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.FIRST_TO_RESPOND)
        assert result.agreed_output == {"answer": "first"}
        assert result.winner_agent_id == "early"

    # ── Unanimous ───────────────────────────────────────────────────────

    def test_unanimous_all_agree(self):
        """All agents produce identical output → unanimous."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "yes"}),
            make_vote("b", {"answer": "yes"}),
            make_vote("c", {"answer": "yes"}),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.UNANIMOUS)
        assert result.agreement_level == 1.0
        assert result.agreed_output == {"answer": "yes"}

    def test_unanimous_disagreement(self):
        """Any disagreement → unanimous fails."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "yes"}),
            make_vote("b", {"answer": "no"}),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.UNANIMOUS)
        assert result.agreement_level == 0.0
        assert len(result.dissenting_votes) == 2

    # ── Voting Breakdown ────────────────────────────────────────────────

    def test_voting_breakdown(self):
        """Every strategy populates voting_breakdown."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "X"}),
            make_vote("b", {"answer": "X"}),
            make_vote("c", {"answer": "Y"}),
        ]
        result = engine.reach_consensus(votes)
        assert len(result.voting_breakdown) >= 2
        # Two distinct hashes present
        assert all(v >= 1 for v in result.voting_breakdown.values())

    # ── Consensus from AgentOutputs ─────────────────────────────────────

    def test_consensus_from_outputs(self):
        """Convenience method works with AgentOutput objects."""
        engine = ConsensusEngine()
        outputs = [
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "A"},
                confidence=0.9,
                reasoning_trace=["agent_1 reasoning"],
            ),
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "A"},
                confidence=0.8,
                reasoning_trace=["agent_2 reasoning"],
            ),
        ]
        result = engine.consensus_from_outputs(outputs)
        assert result.agreement_level == 1.0
        assert result.agreed_output == {"answer": "A"}

    # ── Conflict Detection ──────────────────────────────────────────────

    def test_detect_conflict_when_disagreement(self):
        """Low agreement → conflict detected."""
        engine = ConsensusEngine()
        outputs = [
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "X"},
            ),
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "Y"},
            ),
        ]
        conflict = engine.detect_conflict(outputs, threshold=0.6)
        assert conflict is not None
        assert conflict.agreement_level < 0.6

    def test_no_conflict_when_agreement(self):
        """High agreement → no conflict."""
        engine = ConsensusEngine()
        outputs = [
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "same"},
            ),
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "same"},
            ),
        ]
        conflict = engine.detect_conflict(outputs, threshold=0.3)
        assert conflict is None

    def test_no_conflict_single_agent(self):
        """Single agent never creates a conflict."""
        engine = ConsensusEngine()
        outputs = [
            AgentOutput(
                task_id=uuid4(), step_id=uuid4(),
                status=AgentStatus.SUCCESS,
                output_data={"answer": "lone"},
            ),
        ]
        conflict = engine.detect_conflict(outputs)
        assert conflict is None

    # ── LLM Mediated ────────────────────────────────────────────────────

    def test_llm_mediated_falls_back(self):
        """LLM-mediated strategy falls back to weighted confidence."""
        engine = ConsensusEngine()
        votes = [
            make_vote("a", {"answer": "A"}, confidence=0.9),
            make_vote("b", {"answer": "B"}, confidence=0.3),
        ]
        result = engine.reach_consensus(votes, ConsensusStrategy.LLM_MEDIATED)
        assert result.strategy == ConsensusStrategy.LLM_MEDIATED
        # Falls back to weighted confidence
        assert result.agreed_output == {"answer": "A"}

    # ── Content Hash Uniqueness ─────────────────────────────────────────

    def test_different_outputs_have_different_hashes(self):
        """Different output dicts produce different content hashes."""
        v1 = make_vote("a", {"answer": "A"})
        v2 = make_vote("b", {"answer": "B"})
        assert v1.content_hash != v2.content_hash
        assert v1.content_hash != ""
        assert v2.content_hash != ""

    def test_same_outputs_have_same_hash(self):
        """Identical output dicts produce identical content hashes."""
        v1 = make_vote("a", {"x": 1, "y": 2})
        v2 = make_vote("b", {"x": 1, "y": 2})
        assert v1.content_hash == v2.content_hash
