"""LangGraph state definitions for AgentOS."""
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from datetime import datetime
# LangGraph 1.x: add_messages is in langgraph.graph.message
try:
    from langgraph.graph.message import add_messages
except ImportError:
    # Fallback for older versions (pre-1.x)
    from langgraph.prebuilt import add_messages
from langchain_core.messages import BaseMessage


def merge_dicts(
    a: Optional[Dict[str, Any]] = None, b: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Reducer that merges two dicts for parallel state updates."""
    return {**(a or {}), **(b or {})}


class AgentState(TypedDict, total=False):
    """Shared state passed between all LangGraph nodes."""

    # Identity
    task_id: str
    user_id: str
    trace_id: str

    # Input
    query: str
    config: Dict[str, Any]

    # Conversation / reasoning
    messages: Annotated[List[BaseMessage], add_messages]

    # Planning
    plan: List[Dict[str, Any]]
    current_step_index: int

    # Execution
    steps: List[Dict[str, Any]]
    step_results: Dict[str, Any]
    collaboration_results: Annotated[Dict[str, Any], merge_dicts]
    tool_calls: List[Dict[str, Any]]

    # Verification
    verified: bool
    verification_notes: Optional[str]

    # Human-in-the-loop
    approved: Optional[bool]
    approval_reason: Optional[str]

    # Final output
    result: Dict[str, Any]
    error: Optional[str]

    # Capability system
    capability_assessment: Optional[Dict[str, Any]]
    feasibility_report: Optional[Dict[str, Any]]
    environment_config: Optional[Dict[str, Any]]
    verification_reports: List[Dict[str, Any]]
    recovery_decisions: List[Dict[str, Any]]

    # Metadata
    created_at: str
    mode: str
    status: str

    # Execution config
    max_tool_rounds: int

    # Desktop goal-driven loop tracking
    desktop_iterations: int

    # Approval mode
    approval_mode: Optional[str]

    # Canonical execution state (unified truth for tool/executor/verifier/recovery)
    execution_state: Optional[Dict[str, Any]]

    # ==========================================================================
    # SECTION 5.1: Extended State Fields (Data & State Design)
    # ==========================================================================

    # Task state machine tracking
    task_state: str  # PENDING, PLANNING, EXECUTING, VERIFYING, AWAITING_APPROVAL, COMPLETED, FAILED, REJECTED

    # Idempotency and deduplication
    idempotency_key: Optional[str]  # Unique key for duplicate detection

    # Task priority and complexity
    priority: Optional[str]  # critical, high, normal, low
    complexity_score: Optional[float]  # 0.0-1.0 complexity rating

    # Execution coordination
    execution_lock_id: Optional[str]  # Redis lock identifier for this task
    assigned_agent_id: Optional[str]  # Currently assigned agent

    # Cost tracking (USD)
    cost_estimate_usd: Optional[float]  # Estimated cost before execution
    actual_cost_usd: Optional[float]  # Actual cost after execution

    # Memory and profile linking
    memory_profile_id: Optional[str]  # Link to user's memory profile
    memory_context: Optional[Dict[str, Any]]  # Retrieved memory for this task

    # Artifact tracking
    artifact_refs: Annotated[List[str], lambda a, b: (a or []) + (b or [])]  # Artifact references produced

    # Inter-agent coordination
    handoff_log: Annotated[List[Dict[str, Any]], lambda a, b: (a or []) + (b or [])]  # Inter-agent handoffs
    parent_task_id: Optional[str]  # For sub-task relationships
    child_task_ids: Annotated[List[str], lambda a, b: (a or []) + (b or [])]  # Child tasks spawned

    # Feedback and learning
    feedback_records: Annotated[List[Dict[str, Any]], lambda a, b: (a or []) + (b or [])]  # Past execution feedback

    # Configuration and isolation
    timeout_config: Optional[Dict[str, Any]]  # Per-agent/per-tool/per-workflow timeouts
    isolation_context: Optional[Dict[str, Any]]  # Isolation boundary configuration

    # Audit and compliance
    audit_trail: Annotated[List[Dict[str, Any]], lambda a, b: (a or []) + (b or [])]  # Complete audit log
    compliance_tags: Optional[Dict[str, Any]]  # Compliance-related tags
