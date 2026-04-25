import secrets
import hashlib
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from ...memory.long_term import deployment_repo
from ...api.deps import get_current_user
from ...logs.logger import logger

router = APIRouter(prefix="/deployments", tags=["deployments"])

class CreateDeploymentRequest(BaseModel):
    workflow_id: str
    name: str
    description: Optional[str] = None
    auth_type: str = "none"  # "api_key" | "none"

class DeploymentResponse(BaseModel):
    id: str
    workflow_id: str
    name: str
    description: Optional[str]
    endpoint_url: str
    auth_type: str
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)

@router.post("")
async def create_deployment(body: CreateDeploymentRequest, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    endpoint_path = f"exec/{body.workflow_id}_{secrets.token_urlsafe(8)}"
    api_key = None
    api_key_hash = None
    if body.auth_type == "api_key":
        api_key = f"aos_{secrets.token_urlsafe(32)}"
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    deployment = await deployment_repo.create(
        user_id=user_id,
        workflow_id=body.workflow_id,
        name=body.name,
        endpoint_path=endpoint_path,
        auth_type=body.auth_type,
        api_key_hash=api_key_hash,
        description=body.description,
    )
    
    result = {
        "deployment_id": deployment.id,
        "endpoint_url": f"/public/{deployment.endpoint_path}",
        "api_key": api_key,
    }
    logger.info(f"Deployment created: {deployment.id} for workflow {body.workflow_id}")
    return result

@router.get("")
async def list_deployments(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    deployments = await deployment_repo.list_by_user(user_id)
    return [
        {
            "id": d.id,
            "workflow_id": d.workflow_id,
            "name": d.name,
            "description": d.description,
            "endpoint_url": f"/public/{d.endpoint_path}",
            "auth_type": d.auth_type,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in deployments
    ]

@router.delete("/{deployment_id}")
async def delete_deployment(deployment_id: str, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    deployment = await deployment_repo.get_by_id(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if deployment.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    await deployment_repo.delete(deployment_id)
    return {"success": True}

@router.patch("/{deployment_id}/status")
async def update_deployment_status(deployment_id: str, status: str, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    deployment = await deployment_repo.get_by_id(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if deployment.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    updated = await deployment_repo.update_status(deployment_id, status)
    return {"id": updated.id, "status": updated.status}

@router.post("/mcp")
async def export_mcp(body: CreateDeploymentRequest, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    from ...mcp.server_export import generate_mcp_server
    config = await generate_mcp_server(body.workflow_id, user_id)
    return config
