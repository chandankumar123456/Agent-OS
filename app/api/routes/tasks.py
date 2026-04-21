from fastapi import APIRouter, HTTPException, BackgroundTasks, Header
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio
from ...orchestrator.core import Orchestrator, TaskContext
from ...agents.types import TaskStatus
from ...agents.base import AgentStatus
from ...logs.logger import logger
from ...memory.long_term import task_repo, step_repo
from ...memory.short_term import short_term_memory
from ...config.settings import settings
from ..deps import OrchestratorDep

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
    error: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class TaskCreateBodyResponse(BaseModel):
    task_id: UUID
    status: TaskStatus
    created_at: datetime


TASKS: Dict[UUID, Dict[str, Any]] = {}


async def execute_task_background(
    task_id: UUID,
    query: str,
    config: Dict[str, Any],
    orchestrator: Orchestrator
):
    logger.info(f"Starting background execution for task {task_id}")
    TASKS[task_id]["status"] = TaskStatus.RUNNING
    
    try:
        result = await orchestrator.execute_task(query, config, task_id=task_id)
        
        task_data = TASKS[task_id]
        if result.status == AgentStatus.SUCCESS:
            task_data["status"] = TaskStatus.COMPLETED
            task_data["result"] = result.output_data
            task_data["steps"] = result.output_data.get("steps", [])
        else:
            task_data["status"] = TaskStatus.FAILED
            task_data["error"] = {
                "type": result.error_type,
                "message": result.error_message
            }
        
        logger.info(f"Task {task_id} completed with status: {task_data['status']}")
        
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        TASKS[task_id]["status"] = TaskStatus.FAILED
        TASKS[task_id]["error"] = {"message": str(e)}


def use_celery() -> bool:
    return getattr(settings, 'USE_CELERY', False)


@router.post("", response_model=TaskCreateBodyResponse)
async def create_task(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    orchestrator: OrchestratorDep,
    x_api_key: Optional[str] = Header(None)
):
    task_id = uuid4()
    
    config = request.config.model_dump() if request.config else {}
    config.setdefault("max_steps", 10)
    config.setdefault("timeout", 300)
    
    created_at = datetime.utcnow()
    
    task_data = {
        "task_id": task_id,
        "query": request.query,
        "config": config,
        "status": TaskStatus.PENDING,
        "created_at": created_at,
        "result": None,
        "steps": [],
        "error": None
    }
    
    TASKS[task_id] = task_data
    
    try:
        await task_repo.create(
            task_id=str(task_id),
            query=request.query,
            status=TaskStatus.PENDING.value
        )
    except Exception as e:
        logger.warning(f"Failed to create task in DB: {e}")
    
    if use_celery():
        try:
            from ...queue.tasks import celery_app
            celery_app.send_task(
                "agent_os.execute_task",
                args=[str(task_id), request.query, config],
                task_id=str(task_id)
            )
            logger.info(f"Enqueued task {task_id} to Celery")
        except Exception as e:
            logger.warning(f"Celery enqueue failed, falling back to background task: {e}")
            background_tasks.add_task(
                execute_task_background,
                task_id,
                request.query,
                config,
                orchestrator
            )
    else:
        background_tasks.add_task(
            execute_task_background,
            task_id,
            request.query,
            config,
            orchestrator
        )
    
    logger.info(f"Created task {task_id} for query: {request.query}")
    
    return TaskCreateBodyResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        created_at=created_at
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: UUID):
    if task_id not in TASKS:
        db_task = await task_repo.get(str(task_id))
        if db_task:
            db_steps = await step_repo.get_by_task(str(task_id))
            return TaskStatusResponse(
                task_id=UUID(db_task.id),
                status=TaskStatus(db_task.status),
                result=db_task.result,
                steps=[
                    {
                        "step_id": step.id,
                        "step_number": step.step_number,
                        "agent_type": step.agent_type,
                        "status": step.status,
                        "input_data": step.input_data,
                        "output_data": step.output_data,
                        "confidence": step.confidence,
                    }
                    for step in db_steps
                ],
                error={"message": db_task.error} if db_task.error else None,
                created_at=db_task.created_at
            )
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_data = TASKS[task_id]
    
    return TaskStatusResponse(
        task_id=task_data["task_id"],
        status=task_data["status"],
        result=task_data.get("result"),
        steps=task_data.get("steps"),
        error=task_data.get("error"),
        created_at=task_data.get("created_at")
    )


@router.get("", response_model=List[TaskStatusResponse])
async def list_tasks():
    all_tasks = []
    
    try:
        db_tasks = await task_repo.list_all()
        for db_task in db_tasks:
            db_steps = await step_repo.get_by_task(db_task.id)
            all_tasks.append(TaskStatusResponse(
                task_id=UUID(db_task.id),
                status=TaskStatus(db_task.status),
                result=db_task.result,
                steps=[
                    {
                        "step_id": step.id,
                        "step_number": step.step_number,
                        "agent_type": step.agent_type,
                        "status": step.status,
                        "input_data": step.input_data,
                        "output_data": step.output_data,
                        "confidence": step.confidence,
                    }
                    for step in db_steps
                ],
                error={"message": db_task.error} if db_task.error else None,
                created_at=db_task.created_at
            ))
    except Exception as e:
        logger.warning(f"DB list failed, using in-memory: {e}")
    
    for task_id, task_data in TASKS.items():
        if not any(t.task_id == task_id for t in all_tasks):
            all_tasks.append(TaskStatusResponse(
                task_id=task_data["task_id"],
                status=task_data["status"],
                result=task_data.get("result"),
                steps=task_data.get("steps"),
                error=task_data.get("error"),
                created_at=task_data.get("created_at")
            ))
    
    return all_tasks


@router.delete("/{task_id}")
async def delete_task(task_id: UUID):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")
    
    del TASKS[task_id]
    
    try:
        await short_term_memory.delete_context(str(task_id))
    except Exception as e:
        logger.warning(f"Failed to delete Redis context: {e}")
    
    return {"message": "Task deleted"}


@router.get("/{task_id}/trace")
async def get_task_trace(task_id: UUID):
    for task_data in TASKS.values():
        if task_data["task_id"] == task_id:
            result = task_data.get("result", {})
            trace_id = result.get("trace_id") if result else None
            
            if trace_id:
                from ...logs.tracing import trace_manager
                spans = trace_manager.get_trace(trace_id)
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
                            "error": s.error
                        }
                        for s in spans
                    ]
                }
            
            return {"message": "No trace available", "task_id": str(task_id)}
    
    raise HTTPException(status_code=404, detail="Task not found")
