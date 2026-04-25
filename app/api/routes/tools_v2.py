from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List
from ...tools.v2.schemas import ToolV2
from ...tools.v2.registry import tool_registry_v2
from ...tools.plugins.openapi_ingestor import ingest_openapi_spec
from ...tools.registry import tool_registry
from ...logs.logger import logger
from ...api.deps import get_current_user

router = APIRouter(prefix="/tools/v2", tags=["tools-v2"])


class IngestOpenAPIRequest(BaseModel):
    spec_url: str
    category: str = "api"


class ToolExecuteRequest(BaseModel):
    parameters: Dict[str, Any] = {}


@router.get("/")
async def list_tools(_: object = Depends(get_current_user)) -> Dict[str, Any]:
    tools = await tool_registry_v2.list_all()
    return {"tools": [tool.model_dump() for tool in tools]}


@router.post("/")
async def register_tool(tool: ToolV2, current_user: object = Depends(get_current_user)) -> Dict[str, Any]:
    registered = await tool_registry_v2.register(tool)
    return {"tool": registered.model_dump()}


@router.post("/ingest-openapi")
async def ingest_openapi(request: IngestOpenAPIRequest, current_user: object = Depends(get_current_user)) -> Dict[str, Any]:
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} ingesting OpenAPI spec from {request.spec_url}")
    try:
        tools = await ingest_openapi_spec(request.spec_url, category=request.category)
    except Exception as e:
        logger.error(f"OpenAPI ingestion failed: {e}")
        raise HTTPException(status_code=400, detail=f"OpenAPI ingestion failed: {e}")

    registered_tools: List[ToolV2] = []
    for tool in tools:
        registered = await tool_registry_v2.register(tool)
        registered_tools.append(registered)

    return {
        "tools": [t.model_dump() for t in registered_tools],
        "count": len(registered_tools),
    }


@router.get("/{tool_id}")
async def get_tool(tool_id: str, _: object = Depends(get_current_user)) -> Dict[str, Any]:
    tool = await tool_registry_v2.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return {"tool": tool.model_dump()}


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str, _: object = Depends(get_current_user)) -> Dict[str, Any]:
    tool = await tool_registry_v2.delete(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return {"tool": tool.model_dump(), "deleted": True}


@router.get("/{tool_id}/health")
async def get_tool_health(tool_id: str, _: object = Depends(get_current_user)) -> Dict[str, Any]:
    tool = await tool_registry_v2.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return {"tool_id": tool_id, "health": tool.health.model_dump()}


@router.post("/{tool_id}/execute")
async def execute_tool(tool_id: str, request: ToolExecuteRequest, current_user: object = Depends(get_current_user)) -> Dict[str, Any]:
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} executing v2 tool {tool_id}")
    tool = await tool_registry_v2.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")

    # For native tools that exist in the old registry, delegate there
    if tool.implementation.type.value == "native":
        from ...tools.base import ToolInput
        registered = tool_registry.tools.get(tool_id)
        if registered and registered.tool:
            result = await registered.tool.execute(ToolInput(parameters=request.parameters))
            return {
                "tool_id": tool_id,
                "success": result.success,
                "result": result.result,
                "error": result.error,
                "metadata": result.metadata,
            }

    # For OpenAPI tools, return a mock / proxy structure
    if tool.implementation.type.value == "openapi":
        config = tool.implementation.config
        return {
            "tool_id": tool_id,
            "success": True,
            "result": {
                "mock": True,
                "note": "OpenAPI proxy execution not fully implemented",
                "target": {
                    "method": config.get("method"),
                    "path": config.get("path"),
                    "base_url": config.get("base_url"),
                    "parameters": request.parameters,
                },
            },
            "error": None,
            "metadata": {},
        }

    # Fallback: attempt old registry lookup by name
    from ...tools.base import ToolInput
    result = await tool_registry.execute(tool_id, request.parameters)
    return {
        "tool_id": tool_id,
        "success": result.success,
        "result": result.result,
        "error": result.error,
        "metadata": result.metadata,
    }
