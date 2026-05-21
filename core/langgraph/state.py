"""LangGraph state definitions for AgentOS."""
from typing import TypedDict, List, Dict, Any, Optional, Annotated
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
    # Desktop-Native Simplified State (web-specific metadata removed)
    # ==========================================================================

    # Task state machine tracking (local, not distributed)
    task_state: str  # PENDING, PLANNING, EXECUTING, VERIFYING, AWAITING_APPROVAL, COMPLETED, FAILED, REJECTED

    # Task priority
    priority: Optional[str]  # critical, high, normal, low

    # Cost tracking (USD)
    cost_estimate_usd: Optional[float]  # Estimated cost before execution
    actual_cost_usd: Optional[float]  # Actual cost after execution

    # Memory context (local, not distributed)
    memory_context: Optional[Dict[str, Any]]  # Retrieved memory for this task

    # Artifact references
    artifact_refs: Annotated[List[str], lambda a, b: (a or []) + (b or [])]

    # Sub-task relationships
    parent_task_id: Optional[str]
    child_task_ids: Annotated[List[str], lambda a, b: (a or []) + (b or [])]

    # Feedback records
    feedback_records: Annotated[List[Dict[str, Any]], lambda a, b: (a or []) + (b or [])]

    # Timeout configuration
    timeout_config: Optional[Dict[str, Any]]

    # Audit trail
    audit_trail: Annotated[List[Dict[str, Any]], lambda a, b: (a or []) + (b or [])]
