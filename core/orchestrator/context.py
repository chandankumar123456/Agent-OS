from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime, timezone
from ..agents.types import TaskStatus


class TaskContext:
    def __init__(self, task_id: UUID, user_id: str, query: str, config: Optional[Dict[str, Any]] = None):
        self.task_id = task_id
        self.user_id = user_id
        self.query = query
        self.config = config or {}
        self.mode = self.config.get("mode", "task")
        self.status = TaskStatus.PENDING
        self.steps: List[Dict[str, Any]] = []
        self.context = {"query": query}
        self.result = None
        self.error = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.current_step = 0
        self.trace_id = str(uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "user_id": self.user_id,
            "query": self.query,
            "mode": self.mode,
            "status": self.status.value,
            "steps": self.steps,
            "context": self.context,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
