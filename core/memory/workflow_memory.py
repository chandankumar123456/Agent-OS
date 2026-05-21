from typing import Any, Dict, Optional

from .long_term import workflow_repo, workflow_node_repo


class WorkflowMemory:
    async def get_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        workflow = await workflow_repo.get_by_id(workflow_id)
        if not workflow:
            return None
        return {
            "id": workflow.id,
            "task_id": workflow.task_id,
            "status": workflow.status,
            "definition": workflow.definition,
        }

    async def save_state(
        self,
        workflow_id: str,
        state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        workflow = await workflow_repo.update(workflow_id, definition=state)
        if not workflow:
            return None
        return {
            "id": workflow.id,
            "task_id": workflow.task_id,
            "status": workflow.status,
            "definition": workflow.definition,
        }

    async def get_node_status(self, workflow_id: str, node_id: str) -> Optional[str]:
        node = await workflow_node_repo.get_by_id(node_id)
        if not node or node.workflow_id != workflow_id:
            return None
        return node.status

    async def set_node_status(
        self,
        workflow_id: str,
        node_id: str,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        node = await workflow_node_repo.update(node_id, status=status)
        if not node or node.workflow_id != workflow_id:
            return None
        return {
            "id": node.id,
            "workflow_id": node.workflow_id,
            "status": node.status,
        }


workflow_memory = WorkflowMemory()
