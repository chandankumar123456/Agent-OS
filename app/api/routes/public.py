import hashlib
import json
from fastapi import APIRouter, HTTPException, Header, Request
from typing import Optional
from ...memory.long_term import deployment_repo, workflow_repo
from ...orchestrator.v2.engine import workflow_engine_v2
from ...orchestrator.v2.schemas import WorkflowDefinitionV2
from ...logs.logger import logger

router = APIRouter(tags=["public"])

@router.post("/public/{deployment_path:path}")
async def public_execute(deployment_path: str, request: Request, x_api_key: Optional[str] = Header(None)):
    deployment = await deployment_repo.get_by_path(deployment_path)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if deployment.status != "active":
        raise HTTPException(status_code=403, detail="Deployment is not active")
    
    if deployment.auth_type == "api_key":
        if not x_api_key:
            raise HTTPException(status_code=401, detail="API key required")
        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        if key_hash != deployment.api_key_hash:
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Load workflow definition
    workflow_db = await workflow_repo.get_by_id(deployment.workflow_id)
    if not workflow_db or not workflow_db.definition:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    
    definition = workflow_db.definition
    try:
        payload = await request.json() if await request.body() else {}
    except json.JSONDecodeError:
        payload = {}
    
    # Build WorkflowDefinitionV2 from stored definition
    from ...orchestrator.v2.schemas import WorkflowNodeV2, WorkflowEdgeV2, NodeType
    nodes = []
    for n in definition.get("nodes", []):
        try:
            node_type = NodeType(n.get("node_type", "agent"))
        except ValueError:
            node_type = NodeType.AGENT
        nodes.append(WorkflowNodeV2(
            node_id=str(n.get("id", n.get("node_id", ""))),
            name=n.get("step", n.get("name", "")),
            type=node_type,
            config=n.get("config", {}),
            agent_id=n.get("agent_id", n.get("agent_type", None)),
            tool_bindings=n.get("tool_bindings", []),
            condition=n.get("condition", None),
        ))
    edges = []
    for e in definition.get("edges", []):
        edges.append(WorkflowEdgeV2(
            from_node=str(e.get("from", e.get("from_node", ""))),
            to_node=str(e.get("to", e.get("to_node", ""))),
        ))
    
    workflow_def = WorkflowDefinitionV2(
        workflow_id=deployment.workflow_id,
        name=workflow_db.name or "Deployed Workflow",
        nodes=nodes,
        edges=edges,
    )
    
    context = {"user_id": deployment.user_id, "workflow_id": deployment.workflow_id, "input": payload}
    try:
        result = await workflow_engine_v2.execute(workflow_def, context)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Public execution failed for {deployment_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
