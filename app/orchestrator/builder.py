from typing import Dict, Any, List
from uuid import UUID
from ..memory.long_term import workflow_repo, workflow_node_repo, workflow_edge_repo
from ..logs.logger import logger


class WorkflowBuilder:
    """Builds and persists workflow DAGs from planner steps."""

    async def build(self, task_id: UUID, user_id: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        definition = {"nodes": steps, "edges": []}

        # Check for existing workflow to avoid duplicates on Celery retry
        existing_workflow = await workflow_repo.get_by_task(str(task_id))
        if existing_workflow:
            logger.info(f"Replacing existing workflow {existing_workflow.id} for task {task_id}")
            await workflow_node_repo.delete_by_workflow(existing_workflow.id)
            await workflow_edge_repo.delete_by_workflow(existing_workflow.id)
            workflow = await workflow_repo.update(
                existing_workflow.id,
                definition=definition,
                status="pending",
            )
        else:
            workflow = await workflow_repo.create(
                task_id=str(task_id),
                user_id=user_id,
                name="planner_workflow",
                definition=definition,
            )

        node_rows = []
        node_by_step: Dict[str, str] = {}

        for index, step in enumerate(steps, start=1):
            node = await workflow_node_repo.create(
                workflow_id=workflow.id,
                step_number=index,
                agent_type=step.get("agent_type", "executor"),
                depends_on=[str(dep) for dep in step.get("depends_on", []) if dep is not None],
                input_data={"step": step.get("step", ""), "raw_step": step},
                condition_code=step.get("condition"),
                node_type=step.get("node_type", "agent"),
                approval_config=step.get("approval_config"),
            )
            node_rows.append(node)
            node_by_step[str(step.get("id", index))] = node.id

        for step in steps:
            for dep in step.get("depends_on", []):
                dep_id = node_by_step.get(str(dep))
                current_id = node_by_step.get(str(step.get("id")))
                if dep_id and current_id:
                    await workflow_edge_repo.create(workflow.id, dep_id, current_id)

        return {
            "workflow": workflow,
            "nodes": node_rows,
            "definition": definition,
        }

    @staticmethod
    def validate_definition(definition: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])

        if not nodes:
            errors.append("Workflow must have at least one node")
            return errors

        node_ids = {str(node.get("id")) for node in nodes if node.get("id") is not None}

        for edge in edges:
            from_node = str(edge.get("from")) if edge.get("from") is not None else None
            to_node = str(edge.get("to")) if edge.get("to") is not None else None
            if from_node not in node_ids:
                errors.append(f"Edge references missing source node: {from_node}")
            if to_node not in node_ids:
                errors.append(f"Edge references missing target node: {to_node}")

        adj: Dict[str, List[str]] = {node_id: [] for node_id in node_ids}
        for edge in edges:
            src = str(edge.get("from"))
            dst = str(edge.get("to"))
            if src in adj and dst in adj:
                adj[src].append(dst)

        if not edges:
            for node in nodes:
                node_id = str(node.get("id"))
                for dep in node.get("depends_on", []):
                    dep_str = str(dep)
                    if dep_str in adj:
                        adj[dep_str].append(node_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Cycle detected")
            if node_id in visited:
                return
            visiting.add(node_id)
            for neighbor in adj.get(node_id, []):
                visit(neighbor)
            visiting.remove(node_id)
            visited.add(node_id)

        try:
            for node_id in adj:
                if node_id not in visited:
                    visit(node_id)
        except ValueError:
            errors.append("Workflow contains a cycle")

        return errors

    @staticmethod
    def serialize_state(state: Dict[str, Any]) -> Dict[str, Any]:
        workflow = state.get("workflow")
        def _status_label(value) -> str:
            return value.lower() if isinstance(value, str) else str(value)
        return {
            "workflow": {
                "id": workflow.id if workflow else None,
                "task_id": workflow.task_id if workflow else None,
                "name": workflow.name if workflow else None,
                "definition": workflow.definition if workflow else None,
                "status": _status_label(workflow.status) if workflow else None,
            },
            "nodes": [
                {
                    "id": node.id,
                    "step_number": node.step_number,
                    "agent_type": node.agent_type,
                    "status": _status_label(node.status),
                    "depends_on": node.depends_on,
                    "input_data": node.input_data,
                    "output_data": node.output_data,
                    "confidence": node.confidence,
                    "node_type": getattr(node, "node_type", "agent"),
                    "approval_config": getattr(node, "approval_config", None),
                }
                for node in state.get("nodes", [])
            ],
            "edges": [
                {"id": edge.id, "from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id}
                for edge in state.get("edges", [])
            ],
        }
