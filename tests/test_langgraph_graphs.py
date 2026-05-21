"""Tests for LangGraph graph compilation."""
from core.langgraph.graphs import (
    compile_task_graph,
    compile_autonomous_graph,
    compile_workflow_graph,
    compile_collaboration_graph,
    get_checkpointer,
)
from core.langgraph.checkpointer import PostgresCheckpointSaver


def test_compile_task_graph_returns_compiled_graph():
    graph = compile_task_graph()
    assert graph is not None
    # CompiledStateGraph has an ainvoke method
    assert hasattr(graph, "ainvoke")


def test_compile_autonomous_graph_returns_compiled_graph():
    graph = compile_autonomous_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


def test_compile_workflow_graph_without_definition_falls_back():
    graph = compile_workflow_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


def test_compile_workflow_graph_with_definition():
    definition = {
        "nodes": [
            {"id": "node1", "node_type": "agent"},
            {"id": "node2", "node_type": "agent"},
        ],
        "edges": [
            {"from_node_id": "node1", "to_node_id": "node2"},
        ],
    }
    graph = compile_workflow_graph(workflow_definition=definition)
    assert graph is not None
    assert hasattr(graph, "ainvoke")


def test_compile_collaboration_graph_returns_compiled_graph():
    graph = compile_collaboration_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


def test_get_checkpointer_returns_postgres_saver():
    cp = get_checkpointer()
    assert isinstance(cp, PostgresCheckpointSaver)


def test_graph_cache_reuses_instances():
    from core.langgraph.graphs import get_cached_graph, _graph_cache
    _graph_cache.clear()
    g1 = get_cached_graph("task")
    g2 = get_cached_graph("task")
    assert g1 is g2
