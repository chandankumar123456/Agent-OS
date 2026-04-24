from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional
import asyncio
import ast
from .errors import WorkflowPausedForApproval


NodeRunner = Callable[["WorkflowNode", Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class WorkflowNode:
    id: str
    step: str
    agent_type: str = "executor"
    depends_on: List[str] = field(default_factory=list)
    condition: Optional[str] = None
    step_number: int = 0
    node_type: str = "agent"
    approval_config: Optional[Dict[str, Any]] = None


class WorkflowEngine:
    def __init__(self):
        self.workflows: Dict[str, List[WorkflowNode]] = {}

    def register_workflow(self, name: str, nodes: List[WorkflowNode]) -> None:
        self.workflows[name] = nodes

    def load_workflow(self, spec: Dict[str, Any]) -> List[WorkflowNode]:
        nodes = []
        for index, item in enumerate(spec.get("nodes", []), start=1):
            nodes.append(
                WorkflowNode(
                    id=str(item["id"]),
                    step=item["step"],
                    agent_type=item.get("agent_type", "executor"),
                    depends_on=[str(dep) for dep in item.get("depends_on", [])],
                    condition=item.get("condition"),
                    step_number=int(item.get("step_number", index)),
                    node_type=item.get("node_type", "agent"),
                    approval_config=item.get("approval_config"),
                )
            )
        return nodes

    def validate_graph(self, nodes: List[WorkflowNode]) -> None:
        node_ids = {node.id for node in nodes}

        for node in nodes:
            missing = [dep for dep in node.depends_on if dep not in node_ids]
            if missing:
                raise ValueError(f"invalid dependency: {node.id} depends on missing nodes {missing}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("workflow cycle detected")
            if node_id in visited:
                return
            visiting.add(node_id)
            node = next(item for item in nodes if item.id == node_id)
            for dep in node.depends_on:
                visit(dep)
            visiting.remove(node_id)
            visited.add(node_id)

        for node in nodes:
            visit(node.id)

    def _evaluate_condition(self, node: WorkflowNode, context: Dict[str, Any]) -> bool:
        if not node.condition:
            return True

        expression = node.condition.strip()
        if expression.startswith("lambda"):
            raise ValueError("deterministic conditions must not use lambda expressions")

        tree = ast.parse(expression, mode="eval")

        allowed_binops = (ast.And, ast.Or)
        allowed_boolops = (ast.And, ast.Or)
        allowed_cmpops = (ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE)

        def validate(node: ast.AST) -> None:
            if isinstance(node, ast.Expression):
                validate(node.body)
                return
            if isinstance(node, ast.BoolOp):
                if not isinstance(node.op, allowed_boolops):
                    raise ValueError("invalid boolean operator in condition")
                for value in node.values:
                    validate(value)
                return
            if isinstance(node, ast.UnaryOp):
                if not isinstance(node.op, ast.Not):
                    raise ValueError("invalid unary operator in condition")
                validate(node.operand)
                return
            if isinstance(node, ast.Compare):
                validate(node.left)
                for op in node.ops:
                    if not isinstance(op, allowed_cmpops):
                        raise ValueError("invalid comparison operator in condition")
                for comparator in node.comparators:
                    validate(comparator)
                return
            if isinstance(node, ast.Subscript):
                if not isinstance(node.value, ast.Name) or node.value.id != "context":
                    raise ValueError("only context lookups are allowed in conditions")
                validate(node.slice)
                return
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Attribute):
                    raise ValueError("only context.get calls are allowed in conditions")
                if not isinstance(node.func.value, ast.Name) or node.func.value.id != "context" or node.func.attr != "get":
                    raise ValueError("only context.get calls are allowed in conditions")
                if node.keywords:
                    raise ValueError("keyword arguments are not allowed in conditions")
                for arg in node.args:
                    validate(arg)
                return
            if isinstance(node, ast.Name):
                if node.id != "context":
                    raise ValueError("unknown name in condition")
                return
            if isinstance(node, ast.Constant):
                return
            if isinstance(node, ast.Index):
                validate(node.value)
                return
            if isinstance(node, ast.Slice):
                raise ValueError("slices are not allowed in conditions")
            raise ValueError("unsupported expression in condition")

        validate(tree)

        def evaluate(node: ast.AST) -> Any:
            if isinstance(node, ast.Expression):
                return evaluate(node.body)
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                return context
            if isinstance(node, ast.Subscript):
                base = evaluate(node.value)
                key = evaluate(node.slice)
                return base[key]
            if isinstance(node, ast.BoolOp):
                values = [bool(evaluate(value)) for value in node.values]
                if isinstance(node.op, ast.And):
                    return all(values)
                return any(values)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                return not bool(evaluate(node.operand))
            if isinstance(node, ast.Compare):
                left = evaluate(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = evaluate(comparator)
                    if isinstance(op, ast.Eq) and not (left == right):
                        return False
                    if isinstance(op, ast.NotEq) and not (left != right):
                        return False
                    if isinstance(op, ast.Gt) and not (left > right):
                        return False
                    if isinstance(op, ast.GtE) and not (left >= right):
                        return False
                    if isinstance(op, ast.Lt) and not (left < right):
                        return False
                    if isinstance(op, ast.LtE) and not (left <= right):
                        return False
                    left = right
                return True
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Attribute):
                    raise ValueError("only context.get calls are allowed in conditions")
                base = evaluate(node.func.value)
                if node.func.attr != "get" or base is not context:
                    raise ValueError("only context.get calls are allowed in conditions")
                args = [evaluate(arg) for arg in node.args]
                if len(args) > 2:
                    raise ValueError("context.get accepts at most two positional arguments")
                return context.get(*args)
            raise ValueError("unsupported expression in condition")

        return bool(evaluate(tree))

    def to_execution_plan(self, nodes: List[WorkflowNode], context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        context = context or {}
        self.validate_graph(nodes)
        plan: List[Dict[str, Any]] = []
        for node in nodes:
            if not self._evaluate_condition(node, context):
                continue
            plan.append(
                {
                    "id": node.id,
                    "step": node.step,
                    "agent_type": node.agent_type,
                    "depends_on": node.depends_on,
                    "node_type": node.node_type,
                    "approval_config": node.approval_config,
                }
            )
        return plan

    async def execute_graph(
        self,
        nodes: List[WorkflowNode],
        runtime: Dict[str, Any],
        context: Dict[str, Any],
        max_parallelism: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.validate_graph(nodes)
        node_map = {node.id: node for node in nodes}
        results: Dict[str, Dict[str, Any]] = {
            node.id: {"status": "pending", "depends_on": list(node.depends_on)} for node in nodes
        }
        completed: set[str] = set()
        skipped: set[str] = set()
        running_context = dict(context)
        runner = runtime["run_node"]
        semaphore = asyncio.Semaphore(max_parallelism) if max_parallelism else None

        while len(completed) + len(skipped) < len(nodes):
            ready = [
                node
                for node in sorted(nodes, key=lambda item: item.step_number)
                if results[node.id]["status"] == "pending" and set(node.depends_on).issubset(completed | skipped)
            ]

            if not ready:
                raise RuntimeError("Circular or unsatisfied workflow dependencies")

            runnable: List[WorkflowNode] = []
            for node in ready:
                if self._evaluate_condition(node, running_context):
                    if node.node_type == "wait":
                        results[node.id]["status"] = "waiting_approval"
                        raise WorkflowPausedForApproval(node.id, node.approval_config)
                    runnable.append(node)
                else:
                    results[node.id]["status"] = "skipped"
                    skipped.add(node.id)

            if not runnable:
                continue

            async def execute_node(node: WorkflowNode) -> tuple[str, Dict[str, Any]]:
                if semaphore:
                    async with semaphore:
                        results[node.id]["status"] = "running"
                        output = await runner(node, running_context)
                        return node.id, output
                else:
                    results[node.id]["status"] = "running"
                    output = await runner(node, running_context)
                    return node.id, output

            node_outputs = await asyncio.gather(*(execute_node(node) for node in runnable))

            for node_id, output in node_outputs:
                results[node_id]["status"] = "completed"
                results[node_id]["output"] = output
                completed.add(node_id)

        return {
            "nodes": results,
            "edges": [
                {"from": dep, "to": node.id}
                for node in nodes
                for dep in node.depends_on
            ],
        }

    async def plan(self, query: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        if "workflow" in context and isinstance(context["workflow"], dict):
            nodes = self.load_workflow(context["workflow"])
            return self.to_execution_plan(nodes, context)

        return [
            {"id": "analyze", "step": f"analyze: {query}", "agent_type": "executor", "depends_on": []},
            {"id": "process", "step": f"process: {query}", "agent_type": "executor", "depends_on": ["analyze"]},
            {"id": "finalize", "step": f"finalize: {query}", "agent_type": "executor", "depends_on": ["process"]},
        ]
