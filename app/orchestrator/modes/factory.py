from typing import Dict, Any
from .base import ModeStrategy
from .task import TaskMode
from .workflow import WorkflowMode
from .autonomous import AutonomousMode
from .collaboration import CollaborationMode


class ModeStrategyFactory:
    """Factory for creating mode strategy instances."""

    _strategies: Dict[str, ModeStrategy] = {
        "task": TaskMode(),
        "workflow": WorkflowMode(),
        "autonomous": AutonomousMode(),
        "collaboration": CollaborationMode(),
    }

    @classmethod
    def get(cls, mode: str) -> ModeStrategy:
        if mode not in cls._strategies:
            raise ValueError(
                f"Unknown mode: {mode}. Valid modes: {list(cls._strategies.keys())}"
            )
        return cls._strategies[mode]

    @classmethod
    def list_modes(cls) -> Dict[str, str]:
        return {
            "task": "Standard plan → execute → verify pipeline",
            "workflow": "Predefined workflow execution with checkpoints",
            "autonomous": "Self-directed agent loop with replanning",
            "collaboration": "Multi-agent coordinated execution",
        }
