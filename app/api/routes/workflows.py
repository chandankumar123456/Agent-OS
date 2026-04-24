from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from uuid import uuid4
from ...api.deps import get_current_user
from ...memory.long_term import workflow_repo
from ...logs.logger import logger

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    definition: Dict[str, Any]


class WorkflowCreateResponse(BaseModel):
    id: str
    task_id: str
    name: str
    definition: Dict[str, Any]
    status: str
    created_at: Optional[str] = None


@router.get("")
async def list_workflows(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", ""))
    workflows = await workflow_repo.list_by_user(user_id)
    logger.info(f"User {user_id} listed workflows")
    return {
        "workflows": [
            {
                "id": w.id,
                "task_id": w.task_id,
                "name": w.name,
                "definition": w.definition,
                "status": w.status,
                "created_at": w.created_at.isoformat() if getattr(w, "created_at", None) else None,
            }
            for w in workflows
        ]
    }


@router.post("", response_model=WorkflowCreateResponse)
async def create_workflow(
    request: WorkflowCreateRequest,
    current_user: object = Depends(get_current_user)
):
    user_id = str(getattr(current_user, "id", ""))
    workflow_id = str(uuid4())
    # task_id is required and unique in the DB model; reuse workflow_id as task_id for saved workflows
    workflow = await workflow_repo.create(
        task_id=workflow_id,
        user_id=user_id,
        name=request.name,
        definition=request.definition,
        status="saved",
    )
    logger.info(f"User {user_id} created workflow {workflow_id}")
    return {
        "id": workflow.id,
        "task_id": workflow.task_id,
        "name": workflow.name,
        "definition": workflow.definition,
        "status": workflow.status,
        "created_at": workflow.created_at.isoformat() if getattr(workflow, "created_at", None) else None,
    }


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: object = Depends(get_current_user)
):
    user_id = str(getattr(current_user, "id", ""))
    workflow = await workflow_repo.get_by_id(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "id": workflow.id,
        "task_id": workflow.task_id,
        "name": workflow.name,
        "definition": workflow.definition,
        "status": workflow.status,
        "created_at": workflow.created_at.isoformat() if getattr(workflow, "created_at", None) else None,
    }
