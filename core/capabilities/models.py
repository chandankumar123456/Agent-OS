"""Capability system models and enums for AgentOS."""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class Capability(str, Enum):
    FILE = "file"
    CODE = "code"
    WEB = "web"
    SHELL = "shell"
    WORKFLOW = "workflow"
    DEPLOYMENT = "deployment"
    KNOWLEDGE = "knowledge"
    CHAT = "chat"
    RESEARCH = "research"
    COMMUNICATION = "communication"
    DATA_PROCESSING = "data_processing"
    DESKTOP = "desktop"


class FeasibilityResult(str, Enum):
    EXECUTABLE = "executable"
    PARTIALLY_EXECUTABLE = "partially_executable"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"


class VerificationResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class RecoveryAction(str, Enum):
    RETRY = "retry"
    REPLAN = "replan"
    SWITCH_TOOL = "switch_tool"
    SWITCH_ENVIRONMENT = "switch_environment"
    ESCALATE = "escalate"
    SKIP = "skip"


class ExecutionEnvironment(str, Enum):
    LOCAL = "local"
    SHELL = "shell"
    BROWSER_UI = "browser_ui"      # NEW: real browser automation
    CLOUD_API = "cloud_api"        # RENAMED from BROWSER
    FILE = "file"                  # NEW
    SANDBOX = "sandbox"
    DESKTOP = "desktop"


class CapabilityRequirement(BaseModel):
    capability: Capability
    confidence: float = 1.0
    required_tools: List[str] = []
    optional_tools: List[str] = []
    environment_constraints: List[str] = []


class CapabilityAssessment(BaseModel):
    task_id: str
    query: str
    required_capabilities: List[CapabilityRequirement]
    primary_capability: Capability
    estimated_complexity: int = 1  # 1-10
    safety_flags: List[str] = []


class FeasibilityReport(BaseModel):
    task_id: str
    result: FeasibilityResult
    available_capabilities: List[Capability]
    missing_capabilities: List[Capability]
    available_tools: List[str]
    missing_tools: List[str]
    environment_ready: bool
    safety_passed: bool
    notes: List[str] = []


class VerificationReport(BaseModel):
    task_id: str
    step_id: Optional[str] = None
    result: VerificationResult
    verifier_type: str  # "deterministic" or "llm"
    checks: List[Dict[str, Any]] = []
    evidence: Dict[str, Any] = {}
    failure_reason: Optional[str] = None
    retry_suggested: bool = False


class RecoveryDecision(BaseModel):
    task_id: str
    step_id: Optional[str] = None
    action: RecoveryAction
    reason: str
    next_tool: Optional[str] = None
    next_environment: Optional[ExecutionEnvironment] = None
    max_retries_reached: bool = False
    escalation_reason: Optional[str] = None


class EnvironmentConfig(BaseModel):
    environment: ExecutionEnvironment
    working_dir: Optional[str] = None
    allowed_paths: List[str] = []
    blocked_commands: List[str] = []
    network_access: bool = True
    timeout_seconds: int = 300
    headless: bool = True          # NEW: for browser env
    screenshot_on_complete: bool = False  # NEW
