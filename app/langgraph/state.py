"""LangGraph state definitions for AgentOS."""
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from datetime import datetime
from langgraph.graph.message import add_messages
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
