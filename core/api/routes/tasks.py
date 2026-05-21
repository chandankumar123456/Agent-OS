import asyncio
from enum import Enum
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from ...agents.types import TaskStatus, StepStatus
from ...logs.logger import logger
from ...memory.long_term import task_repo, trace_repo, node_trace_repo, span_repo, workflow_repo, workflow_node_repo, workflow_edge_repo
from ...config.settings import settings
from ...orchestrator.errors import ErrorCode, UnrecoverableError
from ...orchestrator.event_bus import event_bus, Event
from ..deps import OrchestratorDep, get_current_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskMode(str, Enum):
    TASK = "task"
    WORKFLOW = "workflow"
    AUTONOMOUS = "autonomous"
    COLLABORATION = "collaboration"


class TaskConfig(BaseModel):
    max_steps: int = Field(default=10, ge=1, le=100)
    timeout: int = Field(default=300, ge=1, le=3600)


class TaskCreateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    config: Optional[TaskConfig] = None
    mode: TaskMode = Field(default=TaskMode.TASK)


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
    retry_info: Optional[Dict[str, Any]] = None
    fallback_chain: Optional[List[str]] = None
    created_at: Optional[datetime] = None


def _safe_task_status(status_str: str) -> TaskStatus:
    try:
        return TaskStatus(status_str)
    except ValueError:
        return TaskStatus.PENDING


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
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": ErrorCode.TASK_ACCESS_DENIED.value,
                    "message": "Task not found",
                    "context": {}
                }
            }
        )


def _status_label(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _serialize_node(node) -> Dict[str, Any]:
    return {
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


async def _task_scoped_workflow_state(task_id: UUID, current_user: object):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    from ...orchestrator.core import orchestrator
    return await orchestrator._get_workflow_state(task_id)


@router.post("", response_model=TaskCreateResponse)
async def create_task(
    request: TaskCreateRequest,
    orchestrator: OrchestratorDep,
    background_tasks: BackgroundTasks,
    current_user: object = Depends(get_current_user)
):
    user_id = str(getattr(current_user, "id"))

    active_count = await task_repo.count_active_by_user(user_id)
    if active_count >= settings.MAX_ACTIVE_TASKS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": ErrorCode.RATE_LIMIT_EXCEEDED.value,
                    "message": f"Maximum active tasks ({settings.MAX_ACTIVE_TASKS_PER_USER}) reached",
                    "context": {"active_tasks": active_count, "limit": settings.MAX_ACTIVE_TASKS_PER_USER}
                }
            }
        )

    task_id = uuid4()

    config = request.config.model_dump() if request.config else {}
    config.setdefault("max_steps", settings.MAX_STEPS_DEFAULT)
    config.setdefault("timeout", settings.TIMEOUT_DEFAULT)
    config.setdefault("mode", request.mode.value)

    created_at = datetime.now(timezone.utc)

    db_task = await task_repo.create(
        task_id=str(task_id),
        query=request.query,
        user_id=user_id,
        status=TaskStatus.PENDING.value
    )
    created_at = db_task.created_at
    await event_bus.publish(
        f"task:{task_id}",
        Event("task.status_changed", {"status": TaskStatus.PENDING.value, "task_id": str(task_id)})
    )

    if use_celery():
        try:
            from ...queue.tasks import celery_app
            celery_app.send_task(
                "agent_os.execute_task",
                args=[str(task_id), request.query, config, user_id],
                task_id=str(task_id)
            )
            logger.info(f"Enqueued task {task_id} to Celery")
        except Exception as e:
            logger.error(f"Celery enqueue failed: {e}")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "code": ErrorCode.TASK_QUEUE_UNAVAILABLE.value,
                        "message": "Task queue unavailable",
                        "context": {"error": str(e)}
                    }
                }
            )
    else:
        async def _run_task():
            try:
                await task_repo.update(str(task_id), status=TaskStatus.RUNNING.value)
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.status_changed", {"status": TaskStatus.RUNNING.value, "task_id": str(task_id)})
                )
                result = await orchestrator.execute_task(
                    query=request.query,
                    config=config,
                    task_id=task_id,
                    user_id=user_id,
                )
                if result.status.value == "success":
                    await task_repo.update(
                        str(task_id), status=TaskStatus.COMPLETED.value, result=result.output_data
                    )
                    await event_bus.publish(
                        f"task:{task_id}",
                        Event("task.status_changed", {"status": TaskStatus.COMPLETED.value, "task_id": str(task_id)})
                    )
                else:
                    await task_repo.update(
                        str(task_id), status=TaskStatus.FAILED.value, error=result.error_message
                    )
                    await event_bus.publish(
                        f"task:{task_id}",
                        Event("task.status_changed", {"status": TaskStatus.FAILED.value, "task_id": str(task_id)})
                    )
            except UnrecoverableError as e:
                logger.error(f"Task {task_id} blocked by guardrails: {e.message}", task_id=str(task_id))
                await task_repo.update(
                    str(task_id),
                    status=TaskStatus.FAILED.value,
                    error={"code": e.code.value, "message": e.message, "context": e.context}
                )
                await event_bus.publish(
                    f"task:{task_id}",
                    Event("task.status_changed", {"status": TaskStatus.FAILED.value, "task_id": str(task_id)})
                )
            except Exception as e:
                logger.error(f"Background task execution failed: {e}", task_id=str(task_id))
                try:
                    error_detail = getattr(e, 'message', str(e))
                    error_code = getattr(getattr(e, 'code', None), 'value', ErrorCode.EXECUTION_ERROR.value)
                    error_context = getattr(e, 'context', {})
                    # Extract retry and fallback info from error context if available
                    retry_info = error_context.get("retry_info") if isinstance(error_context, dict) else None
                    fallback = error_context.get("fallback_chain") if isinstance(error_context, dict) else None
                    result_data = {}
                    if retry_info:
                        result_data["retry_info"] = retry_info
                    if fallback:
                        result_data["fallback_chain"] = fallback
                    await task_repo.update(
                        str(task_id),
                        status=TaskStatus.FAILED.value,
                        error={"code": error_code, "message": error_detail, "context": error_context},
                        result=result_data if result_data else None
                    )
                    await event_bus.publish(
                        f"task:{task_id}",
                        Event("task.status_changed", {"status": TaskStatus.FAILED.value, "task_id": str(task_id)})
                    )
                except Exception as db_err:
                    logger.error(f"Failed to persist background task failure: {db_err}", task_id=str(task_id))

        background_tasks.add_task(_run_task)
        logger.info(f"Started background task {task_id}")

    logger.info(f"Created task {task_id} for query: {request.query}")

    return TaskCreateResponse(
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
        # Extract retry and fallback context from task result
        retry_info = None
        fallback_chain = None
        if db_task and db_task.result and isinstance(db_task.result, dict):
            retry_info = db_task.result.get("retry_info")
            fallback_chain = db_task.result.get("fallback_chain")
        return TaskStatusResponse(
            task_id=UUID(db_task.id),
            status=_safe_task_status(db_task.status),
            result=db_task.result,
            steps=[_serialize_node(node) for node in workflow_state["nodes"]],
            workflow_state={
                "workflow": {
                    "id": workflow_state["workflow"].id if workflow_state["workflow"] else None,
                    "task_id": workflow_state["workflow"].task_id if workflow_state["workflow"] else None,
                    "name": workflow_state["workflow"].name if workflow_state["workflow"] else None,
                    "definition": workflow_state["workflow"].definition if workflow_state["workflow"] else None,
                    "status": workflow_state["workflow"].status if workflow_state["workflow"] else None,
                },
                "nodes": [_serialize_node(node) for node in workflow_state["nodes"]],
                "edges": [
                    {"id": edge.id, "from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id}
                    for edge in workflow_state["edges"]
                ],
            },
            error={"message": db_task.error} if db_task.error else None,
            retry_info=retry_info,
            fallback_chain=fallback_chain,
            created_at=db_task.created_at,
        )

    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": ErrorCode.TASK_NOT_FOUND.value,
                "message": "Task not found",
                "context": {"task_id": str(task_id)}
            }
        }
    )


@router.get("", response_model=List[TaskStatusResponse])
async def list_tasks(
    current_user: object = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0)
):
    if _is_admin(current_user):
        db_tasks = await task_repo.list_all()
    else:
        db_tasks = await task_repo.list_by_user(str(getattr(current_user, "id")), limit=limit, offset=offset)

    if not db_tasks:
        return []

    # ── Batch fetch all workflow data (N+1 fix) ─────────────────────
    all_task_ids = [str(t.id) for t in db_tasks]
    workflows = await workflow_repo.get_by_task_ids(all_task_ids)
    workflow_by_task_id = {w.task_id: w for w in workflows}

    workflow_ids = [w.id for w in workflows]
    if workflow_ids:
        all_nodes, all_edges = await asyncio.gather(
            workflow_node_repo.get_by_workflow_ids(workflow_ids),
            workflow_edge_repo.get_by_workflow_ids(workflow_ids),
        )
    else:
        all_nodes, all_edges = [], []

    nodes_by_workflow_id = {}
    for node in all_nodes:
        nodes_by_workflow_id.setdefault(node.workflow_id, []).append(node)

    edges_by_workflow_id = {}
    for edge in all_edges:
        edges_by_workflow_id.setdefault(edge.workflow_id, []).append(edge)

    # ── Build response ─────────────────────────────────────────────
    all_tasks = []
    for db_task in db_tasks:
        workflow = workflow_by_task_id.get(str(db_task.id))
        workflow_nodes = nodes_by_workflow_id.get(workflow.id, []) if workflow else []
        workflow_edges = edges_by_workflow_id.get(workflow.id, []) if workflow else []

        retry_info = None
        fallback_chain = None
        if db_task.result and isinstance(db_task.result, dict):
            retry_info = db_task.result.get("retry_info")
            fallback_chain = db_task.result.get("fallback_chain")
        all_tasks.append(TaskStatusResponse(
            task_id=UUID(db_task.id),
            status=_safe_task_status(db_task.status),
            result=db_task.result,
            steps=[_serialize_node(node) for node in workflow_nodes],
            workflow_state={
                "workflow": {
                    "id": workflow.id if workflow else None,
                    "task_id": workflow.task_id if workflow else None,
                    "name": workflow.name if workflow else None,
                    "definition": workflow.definition if workflow else None,
                    "status": workflow.status if workflow else None,
                },
                "nodes": [_serialize_node(node) for node in workflow_nodes],
                "edges": [
                    {"id": edge.id, "from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id}
                    for edge in workflow_edges
                ],
            },
            error={"message": db_task.error} if db_task.error else None,
            retry_info=retry_info,
            fallback_chain=fallback_chain,
            created_at=db_task.created_at
        ))

    return all_tasks


@router.delete("/{task_id}")
async def delete_task(task_id: UUID, current_user: object = Depends(get_current_user)):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    await task_repo.update(str(task_id), status=TaskStatus.CANCELLED.value)

    # Publish cancellation event so running execution paths can listen
    await event_bus.publish(
        f"task:{task_id}",
        Event("task.cancelled", {"task_id": str(task_id), "reason": "Cancelled by user"}, source="api")
    )
    await event_bus.publish(
        f"task:{task_id}",
        Event("task.status_changed", {"status": TaskStatus.CANCELLED.value, "task_id": str(task_id)})
    )

    # Write Redis cancellation key so executor nodes can check
    try:
        from ..memory.short_term import redis_client
        if redis_client and redis_client.client:
            await redis_client.client.setex(
                f"agentos:cancelled:{task_id}", 3600, "1"
            )
    except Exception:
        pass

    # Attempt to revoke Celery task if running
    try:
        from ..queue.tasks import celery_app
        celery_app.control.revoke(str(task_id), terminate=True, signal='SIGTERM')
    except Exception:
        pass

    return {"message": "Task deleted", "task_id": str(task_id)}


@router.post("/{task_id}/approve")
async def approve_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: object = Depends(get_current_user)
):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    if not db_task or db_task.status != TaskStatus.WAITING_APPROVAL.value:
        raise HTTPException(status_code=400, detail="Task is not waiting for approval")

    workflow = await workflow_repo.get_by_task(str(task_id))
    if workflow:
        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        for node in nodes:
            if node.status == StepStatus.WAITING_APPROVAL.value:
                await workflow_node_repo.update(node.id, status=StepStatus.APPROVED.value)

    await task_repo.update(str(task_id), status=TaskStatus.RUNNING.value)
    await event_bus.publish(
        f"task:{task_id}",
        Event("task.status_changed", {"status": TaskStatus.RUNNING.value, "task_id": str(task_id)})
    )

    # Trigger workflow continuation in background so the request returns immediately
    async def _resume_workflow():
        try:
            from ...orchestrator.core import orchestrator
            config = (db_task.result or {}).get("config", {}) if db_task.result else {}
            await orchestrator.execute_task(
                query=db_task.query,
                config={**config, "mode": config.get("mode", "task")},
                task_id=task_id,
                user_id=str(getattr(current_user, "id", "system")),
            )
        except Exception as e:
            logger.error(f"Workflow continuation after approval failed: {e}")

    background_tasks.add_task(_resume_workflow)
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} approved task {task_id}; resuming workflow")
    return {"task_id": str(task_id), "status": "approved"}


@router.post("/{task_id}/reject")
async def reject_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: object = Depends(get_current_user)
):
    db_task = await task_repo.get(str(task_id))
    _ensure_task_access(db_task, current_user)
    if not db_task or db_task.status != TaskStatus.WAITING_APPROVAL.value:
        raise HTTPException(status_code=400, detail="Task is not waiting for approval")

    workflow = await workflow_repo.get_by_task(str(task_id))
    if workflow:
        nodes = await workflow_node_repo.get_by_workflow(workflow.id)
        for node in nodes:
            if node.status == StepStatus.WAITING_APPROVAL.value:
                await workflow_node_repo.update(node.id, status=StepStatus.REJECTED.value)

    await task_repo.update(str(task_id), status=TaskStatus.FAILED.value, error="Approval rejected by user")
    await event_bus.publish(
        f"task:{task_id}",
        Event("task.status_changed", {"status": TaskStatus.FAILED.value, "task_id": str(task_id)})
    )

    # For LangGraph-based executions, resume with rejection so the graph reaches END cleanly
    async def _resume_rejection():
        try:
            from ...orchestrator.core import orchestrator
            config = (db_task.result or {}).get("config", {}) if db_task.result else {}
            await orchestrator._execute_with_langgraph(
                query=db_task.query,
                config={**config, "mode": config.get("mode", "task")},
                task_id=task_id,
                user_id=str(getattr(current_user, "id", "system")),
                mode=config.get("mode", "task"),
                resume_value={"approved": False, "reason": "Rejected by user"},
            )
        except Exception as e:
            logger.warning(f"LangGraph rejection resume failed (non-critical): {e}")

    background_tasks.add_task(_resume_rejection)
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} rejected task {task_id}")
    return {"task_id": str(task_id), "status": "rejected"}


@router.get("/{task_id}/trace")
async def get_task_trace(task_id: UUID, current_user: object = Depends(get_current_user)):
    db_task = await task_repo.get(str(task_id))
    if not db_task:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": ErrorCode.TASK_NOT_FOUND.value,
                    "message": "Task not found",
                    "context": {"task_id": str(task_id)}
                }
            }
        )
    _ensure_task_access(db_task, current_user)

    result = db_task.result if isinstance(db_task.result, dict) else {}
    trace_id = result.get("trace_id")
    if not trace_id:
        return {"message": "No trace available", "task_id": str(task_id)}

    trace_row = await trace_repo.get_by_trace_id(trace_id)
    if not trace_row:
        return {"message": "No trace available", "task_id": str(task_id)}

    spans = await span_repo.get_by_trace(trace_id)
    node_traces = await node_trace_repo.get_by_task(str(task_id))
    workflow_state = await _task_scoped_workflow_state(task_id, current_user)

    return {
        "trace_id": trace_id,
        "task_id": str(task_id),
        "user_id": str(getattr(current_user, "id", "")),
        "status": _status_label(getattr(trace_row, "status", None)),
        "workflow_state": {
            "workflow": {
                "id": workflow_state["workflow"].id if workflow_state["workflow"] else None,
                "task_id": workflow_state["workflow"].task_id if workflow_state["workflow"] else None,
                "name": workflow_state["workflow"].name if workflow_state["workflow"] else None,
                "definition": workflow_state["workflow"].definition if workflow_state["workflow"] else None,
                "status": _status_label(workflow_state["workflow"].status) if workflow_state["workflow"] else None,
            },
            "nodes": [_serialize_node(node) for node in workflow_state["nodes"]],
            "edges": [
                {"id": edge.id, "from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id}
                for edge in workflow_state["edges"]
            ],
        },
        "node_traces": [
            {
                "id": row.id,
                "task_id": row.task_id,
                "user_id": row.user_id,
                "trace_id": row.trace_id,
                "node_id": row.node_id,
                "status": _status_label(row.status),
                "input_data": row.input_data,
                "output_data": row.output_data,
                "error": row.error,
                "started_at": row.started_at.isoformat() if getattr(row, "started_at", None) else None,
                "finished_at": row.finished_at.isoformat() if getattr(row, "finished_at", None) else None,
                "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
                "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
            }
            for row in node_traces
        ],
        "spans": [
            {
                "span_id": s.span_id,
                "operation": s.operation,
                "agent_name": s.agent_name,
                "start_time": s.start_time.isoformat() if getattr(s, "start_time", None) else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "status": s.status,
                "error": s.error,
            }
            for s in spans
        ],
    }
