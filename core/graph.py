"""core.graph - LangGraph wiring and state management.

Merges:
- Graph definitions (app/langgraph/graphs.py)
- Node implementations (app/langgraph/nodes.py)
- AgentState (app/langgraph/state.py)

Slimmed AgentState: web-specific fields (cost_estimate_usd,
execution_lock_id, handoff_log, complexity_score) are moved to
side-tables in core.state rather than the core AgentState struct.
"""

from .langgraph.state import AgentState
from .langgraph.nodes import executor_node, planner_node, verifier_node

__all__ = [
    "AgentState",
    "executor_node",
    "planner_node",
    "verifier_node",
]
