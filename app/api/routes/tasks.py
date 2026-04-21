from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List
from ...orchestrator.core import Orchestrator
from ...agents.types import TaskStatus
from ...logs.logger import logger
from ...memory.long_term import task_repo, trace_repo, span_repo
from ...config.settings import settings
from ..deps import OrchestratorDep, get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskConfig(BaseModel):
    max_steps: int = Field(default=10, ge=1, le=100)
    timeout: int = Field(default=300, ge=1, le=3600)


class TaskCreateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    config: Optional[TaskConfig] = None


class TaskCreateResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    created_at: datetime


class TaskStatusResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    steps: Optional[List[Dict[str, Any]]] = None
    workflow_state: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class TaskCreateBodyResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    created_at: datetime


def _step_dependencies(step: Dict[str, Any]) -> List[int]:
    depends_on = step.get("depends_on", [])
    if not isinstance(depends_on, list):
        return []
    resolved: List[int] = []
    for item in depends_on:
        if isinstance(item, int):
            resolved.append(item)
        elif isinstance(item, str) and item.isdigit():
            resolved.append(int(item))
    return resolved


def _parallel_groups(steps: List[Dict[str, Any]]) -> List[List[int]]:
    groups: List[List[int]] = []
    remaining = set(range(len(steps)))
    completed: set[int] = set()

    while remaining:
        ready = [idx for idx in sorted(remaining) if set(_step_dependencies(steps[idx])).issubset(completed)]
        if not ready:
            ready = [min(remaining)]
        groups.append(ready)
        for idx in ready:
            remaining.discard(idx)
            completed.add(idx)

    return groups


def use_celery() -> bool:
    return getattr(settings, 'USE_CELERY', False)


def _is_admin(user: object) -> bool:
    return getattr(user, "role", "user") == "admin"


def _ensure_task_access(task, user: object) -> None:
    if _is_admin(user):
        return
    if not task or getattr(task, "user_id", None) != getattr(user, "id", None):
        raise HTTPException(status_code=404, detail="Task not found")


async def _task_scoped_workflow_state(task_id: UUID, current_user: object):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    return await Orchestrator()._get_workflow_state(task_id)


@router.post("", response_model=TaskCreateBodyResponse)
async def create_task(
    request: TaskCreateRequest,
    orchestrator: OrchestratorDep,
    current_user: object = Depends(get_current_user)
):
    task_id = uuid4()
    
    config = request.config.model_dump() if request.config else {}
    config.setdefault("max_steps", 10)
    config.setdefault("timeout", 300)
    
    created_at = datetime.utcnow()
    
    db_task = await task_repo.create(
        task_id=str(task_id),
        query=request.query,
        user_id=str(getattr(current_user, "id")),
        status=TaskStatus.PENDING.value
    )
    created_at = db_task.created_at
    
    if use_celery():
        try:
            from ...queue.tasks import celery_app
            celery_app.send_task(
                "agent_os.execute_task",
                args=[str(task_id), request.query, config, str(getattr(current_user, "id"))],
                task_id=str(task_id)
            )
            logger.info(f"Enqueued task {task_id} to Celery")
        except Exception as e:
            logger.warning(f"Celery enqueue failed: {e}")
            raise HTTPException(status_code=503, detail="Task queue unavailable")
    else:
        raise HTTPException(status_code=503, detail="Celery execution is required")
    
    logger.info(f"Created task {task_id} for query: {request.query}")
    
    return TaskCreateBodyResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        created_at=created_at
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: UUID, current_user: object = Depends(get_current_user)):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    if db_task:
        workflow_state = await _task_scoped_workflow_state(task_id, current_user)
        return TaskStatusResponse(
            task_id=UUID(db_task.id),
            status=TaskStatus(db_task.status),
            result=db_task.result,
            steps=[
                {
                    "step_id": node.id,
                    "step_number": node.step_number,
                    "agent_type": node.agent_type,
                    "status": node.status,
                    "input_data": node.input_data,
                    "output_data": node.output_data,
                    "confidence": node.confidence,
                }
                for node in workflow_state["nodes"]
            ],
            workflow_state={
                "workflow": {
                    "id": workflow_state["workflow"].id if workflow_state["workflow"] else None,
                    "task_id": workflow_state["workflow"].task_id if workflow_state["workflow"] else None,
                    "name": workflow_state["workflow"].name if workflow_state["workflow"] else None,
                    "definition": workflow_state["workflow"].definition if workflow_state["workflow"] else None,
                    "status": workflow_state["workflow"].status if workflow_state["workflow"] else None,
                },
                "nodes": [
                    {
                        "id": node.id,
                        "step_number": node.step_number,
                        "agent_type": node.agent_type,
                        "status": node.status,
                        "depends_on": node.depends_on,
                        "input_data": node.input_data,
                        "output_data": node.output_data,
                        "confidence": node.confidence,
                    }
                    for node in workflow_state["nodes"]
                ],
                "edges": [
                    {"id": edge.id, "from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id}
                    for edge in workflow_state["edges"]
                ],
            },
            error={"message": db_task.error} if db_task.error else None,
            created_at=db_task.created_at,
        )

    raise HTTPException(status_code=404, detail="Task not found")


@router.get("", response_model=List[TaskStatusResponse])
async def list_tasks(current_user: object = Depends(get_current_user)):
    db_tasks = await task_repo.list_all()
    all_tasks = []
    
    for db_task in db_tasks:
        if not _is_admin(current_user) and getattr(db_task, "user_id", None) != getattr(current_user, "id", None):
            continue
        workflow_state = await _task_scoped_workflow_state(UUID(db_task.id), current_user)
        all_tasks.append(TaskStatusResponse(
            task_id=UUID(db_task.id),
            status=TaskStatus(db_task.status),
            result=db_task.result,
            steps=[
                {
                    "step_id": node.id,
                    "step_number": node.step_number,
                    "agent_type": node.agent_type,
                    "status": node.status,
                    "input_data": node.input_data,
                    "output_data": node.output_data,
                    "confidence": node.confidence,
                }
                for node in workflow_state["nodes"]
            ],
            workflow_state={
                "workflow": {
                    "id": workflow_state["workflow"].id if workflow_state["workflow"] else None,
                    "task_id": workflow_state["workflow"].task_id if workflow_state["workflow"] else None,
                    "name": workflow_state["workflow"].name if workflow_state["workflow"] else None,
                    "definition": workflow_state["workflow"].definition if workflow_state["workflow"] else None,
                    "status": workflow_state["workflow"].status if workflow_state["workflow"] else None,
                },
                "nodes": [
                    {
                        "id": node.id,
                        "step_number": node.step_number,
                        "agent_type": node.agent_type,
                        "status": node.status,
                        "depends_on": node.depends_on,
                        "input_data": node.input_data,
                        "output_data": node.output_data,
                        "confidence": node.confidence,
                    }
                    for node in workflow_state["nodes"]
                ],
                "edges": [
                    {"id": edge.id, "from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id}
                    for edge in workflow_state["edges"]
                ],
            },
            error={"message": db_task.error} if db_task.error else None,
            created_at=db_task.created_at
        ))
    
    return all_tasks


@router.delete("/{task_id}")
async def delete_task(task_id: UUID, current_user: object = Depends(get_current_user)):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    await task_repo.update(str(task_id), status=TaskStatus.CANCELLED.value)
    
    return {"message": "Task deleted"}


@router.get("/{task_id}/trace")
async def get_task_trace(task_id: UUID, current_user: object = Depends(get_current_user)):
    db_task = await task_repo.get(str(task_id))
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    _ensure_task_access(db_task, current_user)

    result = db_task.result if isinstance(db_task.result, dict) else {}
    trace_id = result.get("trace_id")
    if not trace_id:
        return {"message": "No trace available", "task_id": str(task_id)}

    trace_row = await trace_repo.get_by_trace_id(trace_id)
    if not trace_row:
        return {"message": "No trace available", "task_id": str(task_id)}

    spans = await span_repo.get_by_trace(trace_id)
    if not spans:
        return {"message": "No trace available", "task_id": str(task_id)}

    return {
        "trace_id": trace_id,
        "spans": [
            {
                "span_id": s.span_id,
                "operation": s.operation,
                "agent_name": s.agent_name,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "status": s.status,
                "error": s.error,
            }
            for s in spans
        ],
    }
