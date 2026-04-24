"""LangGraph graph compilers for AgentOS execution modes."""
from typing import Any, Dict, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from .state import AgentState
from .nodes import planner_node, executor_node, verifier_node, approval_node, summarizer_node
from .checkpointer import PostgresCheckpointSaver
from ..logs.logger import logger


def _should_continue(state: AgentState) -> str:
    """Conditional edge: continue executing steps or move to verification."""
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    if idx < len(plan):
        return "execute"
    return "verify"


def _should_approve(state: AgentState) -> str:
    """Conditional edge: check if approval is needed."""
    config = state.get("config", {})
    if config.get("require_approval"):
        return "approve"
    return "summarize"


def _after_approval(state: AgentState) -> str:
    """Conditional edge: after approval, continue or end."""
    approved = state.get("approved")
    if approved is False:
        return "reject"
    return "summarize"


def compile_task_graph(checkpointer: Optional[BaseCheckpointSaver] = None) -> Any:
    """Compile a simple task graph: plan -> execute loop -> verify -> summarize.

    Returns a CompiledStateGraph that can be invoked with ainvoke().
    """
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("approval", approval_node)
    builder.add_node("summarizer", summarizer_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "executor")

    builder.add_conditional_edges(
        "executor",
        _should_continue,
        {"execute": "executor", "verify": "verifier"},
    )

    builder.add_conditional_edges(
        "verifier",
        _should_approve,
        {"approve": "approval", "summarize": "summarizer"},
    )

    builder.add_conditional_edges(
        "approval",
        _after_approval,
        {"summarize": "summarizer", "reject": END},
    )

    builder.add_edge("summarizer", END)

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("Compiled task graph")
    return graph


def compile_autonomous_graph(checkpointer: Optional[BaseCheckpointSaver] = None) -> Any:
    """Compile an autonomous graph that loops with replanning.

    planner -> executor -> (if not done) replanner -> executor -> ... -> verify -> summarize
    """
    from .nodes import planner_node as replanner_node

    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("replanner", replanner_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("approval", approval_node)
    builder.add_node("summarizer", summarizer_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "executor")

    def _autonomous_continue(state: AgentState) -> str:
        plan = state.get("plan", [])
        idx = state.get("current_step_index", 0)
        verified = state.get("verified", False)
        max_steps = state.get("config", {}).get("max_steps", 10)

        if verified:
            return "verify"
        if idx >= len(plan):
            return "replanner"
        if idx >= max_steps:
            return "verify"
        return "execute"

    builder.add_conditional_edges(
        "executor",
        _autonomous_continue,
        {"execute": "executor", "replanner": "replanner", "verify": "verifier"},
    )

    builder.add_edge("replanner", "executor")

    builder.add_conditional_edges(
        "verifier",
        _should_approve,
        {"approve": "approval", "summarize": "summarizer"},
    )

    builder.add_conditional_edges(
        "approval",
        _after_approval,
        {"summarize": "summarizer", "reject": END},
    )

    builder.add_edge("summarizer", END)

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("Compiled autonomous graph")
    return graph


def compile_workflow_graph(
    workflow_definition: Optional[Dict[str, Any]] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> Any:
    """Compile a workflow graph from a workflow definition.

    If no definition is provided, falls back to the standard task graph.
    """
    if not workflow_definition:
        return compile_task_graph(checkpointer=checkpointer)

    builder = StateGraph(AgentState)
    nodes = workflow_definition.get("nodes", [])
    edges = workflow_definition.get("edges", [])

    # Add nodes
    for node in nodes:
        node_id = node.get("id")
        node_type = node.get("node_type", "agent")
        if node_type == "agent":
            builder.add_node(node_id, executor_node)
        elif node_type == "approval":
            builder.add_node(node_id, approval_node)
        else:
            builder.add_node(node_id, executor_node)

    # Add edges
    for edge in edges:
        from_node = edge.get("from_node_id")
        to_node = edge.get("to_node_id")
        if from_node and to_node:
            builder.add_edge(from_node, to_node)

    # Set entry point to first node
    if nodes:
        builder.set_entry_point(nodes[0]["id"])

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("Compiled workflow graph")
    return graph


def compile_collaboration_graph(checkpointer: Optional[BaseCheckpointSaver] = None) -> Any:
    """Compile a collaboration graph with parallel subgraphs.

    Currently delegates to task graph; parallel fan-out/fan-in can be added
    when multi-agent parallel execution is needed.
    """
    # TODO: implement parallel subgraph compilation when needed
    logger.info("Collaboration graph falls back to task graph (parallel mode not yet implemented)")
    return compile_task_graph(checkpointer=checkpointer)


def get_checkpointer() -> PostgresCheckpointSaver:
    """Factory for the default PostgreSQL checkpointer."""
    return PostgresCheckpointSaver()
