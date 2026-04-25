from fastapi import APIRouter, HTTPException, Depends
from ...orchestrator.v2.schemas import WorkflowDefinitionV2
from ...orchestrator.v2.engine import workflow_engine_v2
from ...orchestrator.v2.event_bus import event_bus, Event
from ...api.deps import get_current_user
from ...logs.logger import logger

router = APIRouter(prefix="/workflows/v2", tags=["workflows-v2"])

@router.post("/execute")
async def execute_workflow(workflow: WorkflowDefinitionV2, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    logger.info(f"User {user_id} executing workflow v2 {workflow.workflow_id}")
    result = await workflow_engine_v2.execute(workflow, {"user_id": user_id, "workflow_id": workflow.workflow_id})
    return {"workflow_id": workflow.workflow_id, "result": result}

@router.post("/simulate")
async def simulate_workflow(workflow: WorkflowDefinitionV2, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    logger.info(f"User {user_id} simulating workflow v2 {workflow.workflow_id}")
    result = await workflow_engine_v2.execute(workflow, {"user_id": user_id, "workflow_id": workflow.workflow_id}, dry_run=True)
    return {
        "workflow_id": workflow.workflow_id,
        "path": result.get("path", []),
        "decisions": result.get("decisions", []),
        "estimated_tokens": result.get("estimated_tokens", 0),
        "completed": result.get("completed", []),
        "failed": result.get("failed", []),
    }

@router.post("/validate")
async def validate_workflow(workflow: WorkflowDefinitionV2, _: object = Depends(get_current_user)):
    errors = []
    node_ids = {n.node_id for n in workflow.nodes}
    for edge in workflow.edges:
        if edge.from_node not in node_ids:
            errors.append(f"Edge references missing source: {edge.from_node}")
        if edge.to_node not in node_ids:
            errors.append(f"Edge references missing target: {edge.to_node}")
    if not workflow.nodes:
        errors.append("Workflow must have at least one node")
    # Check for cycles
    adj = {n.node_id: [] for n in workflow.nodes}
    for edge in workflow.edges:
        if edge.from_node in adj:
            adj[edge.from_node].append(edge.to_node)
    visiting = set()
    visited = set()
    def visit(node_id):
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
        for node in workflow.nodes:
            if node.node_id not in visited:
                visit(node.node_id)
    except ValueError:
        errors.append("Workflow contains a cycle")
    return {"valid": len(errors) == 0, "errors": errors}

@router.get("/templates")
async def list_workflow_templates(_: object = Depends(get_current_user)):
    """Return built-in workflow templates for the visual builder."""
    templates = [
        {
            "id": "sequential_review",
            "name": "Sequential Review",
            "definition": {
                "nodes": [
                    {"id": "plan", "name": "Plan review", "type": "agent", "config": {}, "agent_id": "planner"},
                    {"id": "exec", "name": "Execute tasks", "type": "agent", "config": {}, "agent_id": "executor"},
                    {"id": "verify", "name": "Verify output", "type": "agent", "config": {}, "agent_id": "verifier"},
                    {"id": "wait", "name": "Wait for approval", "type": "wait", "config": {"required_role": "admin"}},
                ],
                "edges": [
                    {"from_node": "plan", "to_node": "exec"},
                    {"from_node": "exec", "to_node": "verify"},
                    {"from_node": "verify", "to_node": "wait"},
                ]
            }
        },
        {
            "id": "parallel_research",
            "name": "Parallel Research",
            "definition": {
                "nodes": [
                    {"id": "plan", "name": "Plan research", "type": "agent", "config": {}, "agent_id": "planner"},
                    {"id": "research_a", "name": "Research topic A", "type": "agent", "config": {}, "agent_id": "executor"},
                    {"id": "research_b", "name": "Research topic B", "type": "agent", "config": {}, "agent_id": "executor"},
                    {"id": "synthesize", "name": "Synthesize findings", "type": "agent", "config": {}, "agent_id": "verifier"},
                ],
                "edges": [
                    {"from_node": "plan", "to_node": "research_a"},
                    {"from_node": "plan", "to_node": "research_b"},
                    {"from_node": "research_a", "to_node": "synthesize"},
                    {"from_node": "research_b", "to_node": "synthesize"},
                ]
            }
        },
        {
            "id": "error_recovery",
            "name": "Error Recovery",
            "definition": {
                "nodes": [
                    {"id": "plan", "name": "Plan task", "type": "agent", "config": {}, "agent_id": "planner"},
                    {"id": "exec", "name": "Execute", "type": "agent", "config": {}, "agent_id": "executor"},
                    {"id": "decide", "name": "Check success?", "type": "decision", "config": {"condition": "context.get('status') == 'success'"}},
                    {"id": "retry", "name": "Retry on failure", "type": "agent", "config": {}, "agent_id": "executor"},
                    {"id": "notify", "name": "Notify admin", "type": "wait", "config": {"required_role": "admin"}},
                ],
                "edges": [
                    {"from_node": "plan", "to_node": "exec"},
                    {"from_node": "exec", "to_node": "decide"},
                    {"from_node": "decide", "to_node": "retry", "label": "false"},
                    {"from_node": "retry", "to_node": "notify"},
                ]
            }
        },
    ]
    return {"templates": templates}


@router.get("/{workflow_id}/events")
async def stream_workflow_events(workflow_id: str, _: object = Depends(get_current_user)):
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def event_generator():
        try:
            async for event in event_bus.subscribe(f"workflow:{workflow_id}"):
                yield f"data: {event.json()}\n\n"
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
