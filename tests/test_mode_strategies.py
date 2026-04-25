import pytest
from app.orchestrator.modes.factory import ModeStrategyFactory


def test_mode_strategy_factory_lists_modes():
    modes = ModeStrategyFactory.list_modes()
    assert "task" in modes
    assert "workflow" in modes
    assert "autonomous" in modes
    assert "collaboration" in modes


def test_mode_strategy_factory_returns_task_mode():
    strategy = ModeStrategyFactory.get("task")
    assert strategy is not None


def test_mode_strategy_factory_returns_workflow_mode():
    strategy = ModeStrategyFactory.get("workflow")
    assert strategy is not None


def test_mode_strategy_factory_returns_autonomous_mode():
    strategy = ModeStrategyFactory.get("autonomous")
    assert strategy is not None


def test_mode_strategy_factory_returns_collaboration_mode():
    strategy = ModeStrategyFactory.get("collaboration")
    assert strategy is not None


def test_mode_strategy_factory_raises_on_invalid_mode():
    with pytest.raises(ValueError, match="Unknown mode"):
        ModeStrategyFactory.get("invalid_mode")
