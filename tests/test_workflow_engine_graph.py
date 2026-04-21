import asyncio

from app.orchestrator.workflow import WorkflowEngine


def test_load_workflow_keeps_nodes_and_edges():
    engine = WorkflowEngine()
    spec = {
        "name": "demo",
        "nodes": [
            {"id": "a", "step": "one", "agent_type": "executor", "depends_on": []},
            {"id": "b", "step": "two", "agent_type": "executor", "depends_on": ["a"], "condition": "context['enabled']"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }

    workflow = engine.load_workflow(spec)

    assert len(workflow) == 2
    assert workflow[1].depends_on == ["a"]
    assert workflow[1].condition == "context['enabled']"


def test_validate_graph_rejects_cycles():
    engine = WorkflowEngine()
    workflow = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "depends_on": ["b"]},
                {"id": "b", "step": "two", "depends_on": ["a"]},
            ]
        }
    )

    try:
        engine.validate_graph(workflow)
        assert False, "expected cycle validation to fail"
    except ValueError as exc:
        assert "cycle" in str(exc).lower()


def test_validate_graph_rejects_invalid_dependencies():
    engine = WorkflowEngine()
    workflow = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "depends_on": ["missing"]},
            ]
        }
    )

    try:
        engine.validate_graph(workflow)
        assert False, "expected invalid dependency validation to fail"
    except ValueError as exc:
        assert "dependency" in str(exc).lower()


def test_to_execution_plan_skips_false_conditions():
    engine = WorkflowEngine()
    nodes = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "agent_type": "executor"},
                {"id": "b", "step": "two", "agent_type": "executor", "condition": "context['enabled']"},
            ]
        }
    )

    plan = engine.to_execution_plan(nodes, {"enabled": False})

    assert [item["id"] for item in plan] == ["a"]


def test_to_execution_plan_rejects_lambda_conditions():
    engine = WorkflowEngine()
    nodes = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "condition": "lambda context: True"},
            ]
        }
    )

    try:
        engine.to_execution_plan(nodes, {})
        assert False, "expected lambda conditions to be rejected"
    except ValueError as exc:
        assert "deterministic" in str(exc).lower()


def test_execute_graph_runs_dependencies_before_dependents_and_skips_false_conditions():
    engine = WorkflowEngine()
    workflow = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "agent_type": "executor"},
                {"id": "b", "step": "two", "agent_type": "executor", "depends_on": ["a"]},
                {"id": "c", "step": "three", "agent_type": "executor", "depends_on": ["a"], "condition": "context['enabled']"},
            ],
            "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "c"}],
        }
    )

    seen = []

    async def run_node(node, context):
        seen.append(node.id)
        await asyncio.sleep(0)
        return {"node_id": node.id}

    result = asyncio.run(engine.execute_graph(workflow, {"run_node": run_node}, {"enabled": False}))

    assert seen == ["a", "b"]
    assert result["nodes"]["c"]["status"] == "skipped"
    assert result["nodes"]["b"]["status"] == "completed"


def test_execute_graph_treats_skipped_dependencies_as_satisfied():
    engine = WorkflowEngine()
    workflow = engine.load_workflow(
        {
            "nodes": [
                {"id": "a", "step": "one", "agent_type": "executor"},
                {"id": "b", "step": "two", "agent_type": "executor", "depends_on": ["a"], "condition": "context['enabled']"},
                {"id": "c", "step": "three", "agent_type": "executor", "depends_on": ["b"]},
            ]
        }
    )

    seen = []

    async def run_node(node, context):
        seen.append(node.id)
        return {"node_id": node.id}

    result = asyncio.run(engine.execute_graph(workflow, {"run_node": run_node}, {"enabled": False}))

    assert seen == ["a", "c"]
    assert result["nodes"]["b"]["status"] == "skipped"
    assert result["nodes"]["c"]["status"] == "completed"
