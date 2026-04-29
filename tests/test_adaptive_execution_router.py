import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.agents.base import AgentStatus
from app.orchestrator.adaptive_routing import (
    ExecutionReport,
    ExecutionTier,
    TaskComplexityRouter,
    TaskIntent,
    TaskRoutingDecision,
)
from app.orchestrator.task_runner import TaskRunner


def test_router_open_notepad_routes_tier0():
    router = TaskComplexityRouter()
    decision = router.classify("open notepad")

    assert decision.tier == ExecutionTier.DIRECT
    assert decision.intents[0].kind == "open_app"


def test_router_open_notepad_and_type_hello_routes_tier1():
    router = TaskComplexityRouter()
    decision = router.classify("open notepad and type hello")

    assert decision.tier == ExecutionTier.SEQUENTIAL
    assert [intent.kind for intent in decision.intents] == ["open_app", "type_text"]


def test_router_open_notepad_and_write_hello_world_routes_tier1():
    router = TaskComplexityRouter()
    decision = router.classify("open notepad and write hello world")

    assert decision.tier == ExecutionTier.SEQUENTIAL
    assert [intent.kind for intent in decision.intents] == ["open_app", "type_text"]
    assert decision.intents[1].argument == "hello world"


def test_router_open_write_and_draw_ascii_routes_tier1_chained_output():
    router = TaskComplexityRouter()
    decision = router.classify(
        "open notepad and write hello world and below draw ascii cat"
    )

    assert decision.tier == ExecutionTier.SEQUENTIAL
    assert [intent.kind for intent in decision.intents] == [
        "open_app",
        "type_text",
        "press_key",
        "generate_ascii_art",
    ]
    assert decision.intents[1].argument == "hello world"
    assert decision.intents[3].argument == "cat"


def test_router_open_write_and_draw_ascii_doctor_doom_routes_tier1():
    router = TaskComplexityRouter()
    decision = router.classify(
        "open notepad and write how ai agents will rule the world and below draw ascii doctor doom throne"
    )

    assert decision.tier == ExecutionTier.SEQUENTIAL
    assert [intent.kind for intent in decision.intents] == [
        "open_app",
        "type_text",
        "press_key",
        "generate_ascii_art",
    ]
    assert decision.intents[1].argument == "how ai agents will rule the world"
    assert "doctor doom" in (decision.intents[3].argument or "")


def test_router_search_ai_news_routes_tier1():
    router = TaskComplexityRouter()
    decision = router.classify("search AI news")

    assert decision.tier == ExecutionTier.SEQUENTIAL
    assert decision.intents[0].kind == "search"


def test_router_benchmark_workflow_routes_tier2():
    router = TaskComplexityRouter()
    decision = router.classify("find docs summarize generate webpage preview")

    assert decision.tier == ExecutionTier.FULL_RUNTIME


@pytest.mark.asyncio
async def test_runner_tier0_failure_escalates_to_tier1_success():
    runner = TaskRunner()
    task_id = uuid4()

    # Mock Action V1 to fail with unknown capability so adaptive routing is exercised
    from app.action_v1.models import ActionResult, ActionStatus, Capability
    runner.action_v1.run = AsyncMock(return_value=ActionResult(
        status=ActionStatus.FAILURE,
        task_id=str(task_id),
        error="mock action v1 failure",
    ))
    runner.action_v1.selector.classify = MagicMock(return_value=Capability.UNKNOWN)

    decision = TaskRoutingDecision(
        tier=ExecutionTier.DIRECT,
        reason="single atomic",
        intents=(TaskIntent(kind="open_app", argument="notepad"),),
    )

    runner.task_complexity_router.classify = MagicMock(return_value=decision)
    runner.direct_executor.execute = AsyncMock(return_value=ExecutionReport(
        success=False,
        execution_path="tier_0_direct",
        tier=ExecutionTier.DIRECT,
        actions=[{"tool": "desktop_env__open_application", "success": False}],
        error="headless",
    ))
    runner.sequential_executor.execute = AsyncMock(return_value=ExecutionReport(
        success=True,
        execution_path="tier_1_sequential",
        tier=ExecutionTier.SEQUENTIAL,
        actions=[{"tool": "desktop_env__open_application", "success": True}],
        verification={"all_actions_succeeded": True},
    ))

    with patch("app.orchestrator.task_runner.event_bus.publish", new=AsyncMock()), \
         patch("app.orchestrator.task_runner.capability_router.classify", new=MagicMock()) as mock_capability:
        result = await runner.run("open notepad", {}, task_id, "user-1", "task")

    assert result.status == AgentStatus.SUCCESS
    assert result.output_data["execution_path"] == "tier_1_sequential"
    runner.direct_executor.execute.assert_awaited_once()
    runner.sequential_executor.execute.assert_awaited_once()
    mock_capability.assert_not_called()


@pytest.mark.asyncio
async def test_runner_tier1_failure_escalates_to_tier2_langgraph():
    runner = TaskRunner()
    task_id = uuid4()

    # Mock Action V1 to fail with unknown capability so adaptive routing escalates to LangGraph
    from app.action_v1.models import ActionResult, ActionStatus, Capability
    runner.action_v1.run = AsyncMock(return_value=ActionResult(
        status=ActionStatus.FAILURE,
        task_id=str(task_id),
        error="mock action v1 failure",
    ))
    runner.action_v1.selector.classify = MagicMock(return_value=Capability.UNKNOWN)

    decision = TaskRoutingDecision(
        tier=ExecutionTier.SEQUENTIAL,
        reason="small flow",
        intents=(TaskIntent(kind="search", argument="ai news"),),
    )

    runner.task_complexity_router.classify = MagicMock(return_value=decision)
    runner.sequential_executor.execute = AsyncMock(return_value=ExecutionReport(
        success=False,
        execution_path="tier_1_sequential",
        tier=ExecutionTier.SEQUENTIAL,
        actions=[{"tool": "browser_env__search", "success": False}],
        error="browser error",
    ))

    assessment = MagicMock(
        primary_capability=MagicMock(value="web"),
        estimated_complexity=3,
        safety_flags=[],
        model_dump=lambda: {},
    )
    feasibility = MagicMock(
        result=MagicMock(value="executable"),
        notes=[],
        model_dump=lambda: {},
    )
    env_config = MagicMock(
        environment=MagicMock(value="local"),
        working_dir=None,
        model_dump=lambda: {},
    )

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value={
        "result": {"summary": "ok"},
        "error": None,
        "verified": True,
        "status": "completed",
    })

    with patch("app.orchestrator.task_runner.event_bus.publish", new=AsyncMock()), \
         patch("app.orchestrator.task_runner.capability_router.classify", return_value=assessment), \
         patch("app.orchestrator.task_runner.feasibility_engine.check", new=AsyncMock(return_value=feasibility)), \
         patch("app.orchestrator.task_runner.feasibility_engine.select_environment", return_value=env_config), \
         patch("app.orchestrator.task_runner.execution_environment.configure", new=MagicMock()), \
         patch("app.orchestrator.task_runner.execution_environment.cleanup", new=MagicMock()), \
         patch("app.orchestrator.task_runner.get_checkpointer", return_value=MagicMock()), \
         patch("app.orchestrator.task_runner.get_cached_graph", return_value=mock_graph):
        result = await runner.run("search AI news", {}, task_id, "user-1", "task")

    assert result.status == AgentStatus.SUCCESS
    assert result.output_data == {"summary": "ok"}
    runner.sequential_executor.execute.assert_awaited_once()
    mock_graph.ainvoke.assert_awaited_once()
