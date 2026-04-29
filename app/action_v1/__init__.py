"""Action V1 — Natural-language computer control system.

Architecture:
  User Task → Capability Selector → Deterministic Executor → Verification → Result
                              ↓
                    Vision Fallback (on failure)
                              ↓
                    Human Fallback (dangerous actions)
"""
from .models import Capability, ActionResult, ExecutionContext
from .selector import CapabilitySelector
from .executor import DeterministicExecutor
from .verifier import DeterministicVerifier
from .fallback import VisionFallback, HumanFallback
from .runner import ActionV1Runner

__all__ = [
    "Capability",
    "ActionResult",
    "ExecutionContext",
    "CapabilitySelector",
    "DeterministicExecutor",
    "DeterministicVerifier",
    "VisionFallback",
    "HumanFallback",
    "ActionV1Runner",
]
