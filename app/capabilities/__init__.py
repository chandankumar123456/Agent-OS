"""AgentOS Capability System — verification and recovery only.

Keyword-based routing (CapabilityRouter, FeasibilityEngine, EnvironmentSelector)
has been removed. All planning and environment selection is LLM-driven.
"""
from .models import (
    Capability,
    CapabilityRequirement,
    CapabilityAssessment,
    FeasibilityResult,
    FeasibilityReport,
    VerificationResult,
    VerificationReport,
    RecoveryAction,
    RecoveryDecision,
    ExecutionEnvironment,
    EnvironmentConfig,
)
from .verification import DeterministicVerificationEngine, verification_engine
from .recovery import RecoveryEngine, recovery_engine

__all__ = [
    "Capability",
    "CapabilityRequirement",
    "CapabilityAssessment",
    "FeasibilityResult",
    "FeasibilityReport",
    "VerificationResult",
    "VerificationReport",
    "RecoveryAction",
    "RecoveryDecision",
    "ExecutionEnvironment",
    "EnvironmentConfig",
    "DeterministicVerificationEngine",
    "verification_engine",
    "RecoveryEngine",
    "recovery_engine",
]
