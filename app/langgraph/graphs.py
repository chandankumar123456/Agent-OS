"""LangGraph graph compilers for AgentOS execution modes."""
import json
from typing import Any, Dict, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Send

from .state import AgentState
from .nodes import planner_node, executor_node, verifier_node, approval_node, summarizer_node
from .checkpointer import PostgresCheckpointSaver
from ..logs.logger import logger
from ..agents.llm_client import get_llm_client

_graph_cache: Dict[str, Any] = {}


def get_cached_graph(mode: str, **kwargs) -> Any:
    """Return a pre-compiled graph for the given mode."""
    cache_key = f"{mode}:{hash(str(sorted(kwargs.items())))}"
    if cache_key in _graph_cache:
        return _graph_cache[cache_key]

    if mode == "task":
        graph = compile_task_graph(**kwargs)
    elif mode == "autonomous":
        graph = compile_autonomous_graph(**kwargs)
    elif mode == "workflow":
        graph = compile_workflow_graph(**kwargs)
    elif mode == "collaboration":
        graph = compile_collaboration_graph(**kwargs)
    else:
        graph = compile_task_graph(**kwargs)

    _graph_cache[cache_key] = graph
    return graph


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
        # Check per-session approval mode
        task_id = state.get("task_id", "")
        from ..safety.approval_store import approval_store
        mode = approval_store.get_mode(task_id)
        if mode.value == "full_trust":
            logger.info(f"[_should_approve] Full-trust mode for task {task_id}, skipping approval node")
            return "summarize"
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
    if not nodes:
        raise ValueError("Workflow must have at least one node")
    builder.set_entry_point(nodes[0]["id"])

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("Compiled workflow graph")
    return graph


def compile_collaboration_graph(
    collaboration_config: Optional[Dict[str, Any]] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> Any:
    """Compile a collaboration graph with parallel fan-out/fan-in using Send.

    Flow: distributor -> parallel workers (via Send) -> aggregator -> summarizer.
    """
    config = collaboration_config or {}
    agents = config.get("agents", [])
    merge_strategy = config.get("merge_strategy", "summarize")

    if not agents:
        logger.info("Collaboration graph: no agents configured; falling back to task graph")
        return compile_task_graph(checkpointer=checkpointer)

    async def distributor_node(state: AgentState) -> Dict[str, Any]:
        """Entry point: initialize collaboration state."""
        task_id = state.get("task_id", "")
        logger.info(f"[distributor_node] Distributing to {len(agents)} agents for task {task_id}")
        return {
            "status": "distributing",
            "collaboration_results": {},
        }

    async def worker_node(state: AgentState) -> Dict[str, Any]:
        """Process the query through AgentRuntime (no direct LLM bypass)."""
        from uuid import UUID, uuid4
        from ..runtime.runtime import AgentRuntime
        from ..agents.base import AgentInput, AgentRole, AgentStatus

        task_id = state.get("task_id", "")
        query = state.get("query", "")
        agent_config = state.get("agent_config", {})
        agent_id = agent_config.get("agent_id", "unknown")
        role = agent_config.get("role", "assistant")
        prompt = agent_config.get("prompt", "")

        logger.info(f"[worker_node] Agent {agent_id} ({role}) executing for task {task_id} via runtime")

        runtime = AgentRuntime()
        worker = runtime.get("core_executor")
        if worker is None:
            logger.error(f"[worker_node] No core_executor in runtime for task {task_id}")
            return {
                "collaboration_results": {
                    agent_id: {
                        "role": role,
                        "result": "Error: AgentRuntime not initialized",
                    }
                },
            }

        try:
            task_uuid = UUID(str(task_id)) if task_id else uuid4()
        except (ValueError, TypeError):
            task_uuid = uuid4()

        input_data = AgentInput(
            task_id=task_uuid,
            step_id=uuid4(),
            role=AgentRole.EXECUTOR,
            input_data={
                "step": query,
                "tools": [],
            },
            context={
                "collaboration_agent_id": agent_id,
                "collaboration_role": role,
                "collaboration_prompt": prompt,
                "mode": "collaboration",
            },
        )

        try:
            output = await worker.execute(input_data)
            if output.status == AgentStatus.SUCCESS:
                result_data = output.output_data
                result = (
                    result_data.get("result")
                    or result_data.get("answer")
                    or json.dumps(result_data)
                ) if isinstance(result_data, dict) else str(result_data)
            else:
                result = f"Error during execution: {output.error_message}"
        except Exception as e:
            logger.error(f"[worker_node] Agent {agent_id} failed via runtime: {e}")
            result = f"Error during execution: {e}"

        return {
            "collaboration_results": {
                agent_id: {
                    "role": role,
                    "result": result,
                }
            },
        }

    async def aggregator_node(state: AgentState) -> Dict[str, Any]:
        """Wait for all workers and merge their outputs."""
        task_id = state.get("task_id", "")
        results = state.get("collaboration_results", {})

        logger.info(f"[aggregator_node] Aggregating {len(results)} worker results for task {task_id}")

        if merge_strategy == "concatenate":
            merged_output = "\n\n---\n\n".join(
                f"[{info['role']}]: {info['result']}"
                for info in results.values()
            )
        else:
            # Default summarize: pass structured data to the summarizer
            merged_output = json.dumps(
                {aid: info["result"] for aid, info in results.items()},
                indent=2,
            )

        return {
            "steps": [
                {
                    "step_number": 1,
                    "description": "Collaboration aggregation",
                    "output": merged_output,
                }
            ],
            "status": "aggregated",
        }

    def _distribute_to_workers(state: AgentState) -> List[Send]:
        """Fan-out: return Send objects to invoke worker_node for each agent."""
        return [
            Send("worker", {"agent_config": agent})
            for agent in agents
        ]

    builder = StateGraph(AgentState)
    builder.add_node("distributor", distributor_node)
    builder.add_node("worker", worker_node)
    builder.add_node("aggregator", aggregator_node)
    builder.add_node("summarizer", summarizer_node)

    builder.set_entry_point("distributor")
    builder.add_conditional_edges("distributor", _distribute_to_workers, ["worker"])
    builder.add_edge("worker", "aggregator")
    builder.add_edge("aggregator", "summarizer")
    builder.add_edge("summarizer", END)

    graph = builder.compile(checkpointer=checkpointer)
    logger.info("Compiled collaboration graph")
    return graph


_checkpointer_instance: Optional[PostgresCheckpointSaver] = None


def get_checkpointer() -> PostgresCheckpointSaver:
    """Factory for the default PostgreSQL checkpointer."""
    global _checkpointer_instance
    if _checkpointer_instance is None:
        _checkpointer_instance = PostgresCheckpointSaver()
    return _checkpointer_instance
