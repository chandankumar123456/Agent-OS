import asyncio
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from ...tools.registry import tool_registry
from ...tools.base import BaseTool, ToolInput, ToolOutput
from ...api.deps import get_current_user
from ...memory.long_term import tool_repo
from ...mcp.registry import mcp_registry
from ...logs.logger import logger

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolInfo(BaseModel):
    name: str
    description: str
    type: str
    status: str
    parameters: Dict[str, Any]
    category: str = "general"
    version: str = "1.0.0"
    health_status: str = "unknown"
    tags: List[str] = []


class ToolRegisterRequest(BaseModel):
    name: str
    description: str
    type: str = "custom"
    parameters_schema: Dict[str, Any] = {}
    template: Optional[str] = None


class ToolExecuteRequest(BaseModel):
    parameters: Dict[str, Any] = {}


class ToolRegisterResponse(BaseModel):
    success: bool
    tool: ToolInfo


class MCPServerRegisterRequest(BaseModel):
    name: str
    endpoint: str
    tools_list: Optional[List[Dict[str, Any]]] = None
    auth_scope: Optional[str] = None
    version: str = "1.0.0"


class MCPServerInfo(BaseModel):
    id: str
    name: str
    endpoint: str
    tools_list: Optional[List[Dict[str, Any]]] = None
    auth_scope: Optional[str] = None
    health_status: str
    version: str
    status: str
    updated_at: Optional[str] = None


class DynamicTool(BaseTool):
    def __init__(self, name: str, description: str, parameters_schema: Dict[str, Any], template: Optional[str] = None):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.template = template
        self.tool_type = "custom"
        from ...tools.sandbox import ToolSandbox
        self._sandbox = ToolSandbox()

    async def execute(self, tool_input: ToolInput):
        if not self.template:
            return ToolOutput(
                success=True,
                result={
                    "tool": self.name,
                    "parameters": tool_input.parameters,
                    "template": None,
                },
            )
        return await self._sandbox.run(self.name, self.template, tool_input.parameters)


@router.get("", response_model=List[ToolInfo])
async def list_tools(_: object = Depends(get_current_user)):
    registry_tools = tool_registry.list_tools()
    db_tools = await tool_repo.list_all()

    registry_names = {t["name"] for t in registry_tools}

    combined = list(registry_tools)

    for t in db_tools:
        if t.name not in registry_names:
            combined.append(ToolInfo(
                name=t.name,
                description=t.description,
                type=getattr(t, "type", getattr(t, "tool_type", "unknown")),
                status=getattr(t, "status", "active"),
                parameters=getattr(t, "parameters_schema", {}) or {},
                category=getattr(t, "category", "general"),
                version=getattr(t, "version", "1.0.0"),
                health_status=getattr(t, "health_status", "unknown"),
                tags=getattr(t, "tags", []),
            ).model_dump())

    return combined


@router.post("/mcp-servers", response_model=MCPServerInfo)
async def register_mcp_server(request: MCPServerRegisterRequest, current_user: object = Depends(get_current_user)):
    try:
        server = await mcp_registry.register(
            name=request.name,
            endpoint=request.endpoint,
            tools_list=request.tools_list,
            auth_scope=request.auth_scope,
            version=request.version,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} registered MCP server {request.name}")
    return MCPServerInfo(**server)


@router.get("/mcp-servers", response_model=List[MCPServerInfo])
async def list_mcp_servers(_: object = Depends(get_current_user)):
    servers = await mcp_registry.list_all()
    return [MCPServerInfo(**s) for s in servers]


@router.get("/mcp-servers/{name}", response_model=MCPServerInfo)
async def get_mcp_server(name: str, _: object = Depends(get_current_user)):
    server = await mcp_registry.get(name)
    if not server:
        raise HTTPException(status_code=404, detail=f"MCP server {name} not found")
    return MCPServerInfo(**server)


@router.get("/mcp-servers/{name}/health")
async def check_mcp_server_health(name: str, _: object = Depends(get_current_user)):
    status = await mcp_registry.health_check(name)
    return {"name": name, "health_status": status}


@router.get("/mcp-servers/{name}/tools", response_model=List[Dict[str, Any]])
async def discover_mcp_server_tools(name: str, _: object = Depends(get_current_user)):
    tools = await mcp_registry.discover_tools(name)
    return tools


@router.get("/categories")
async def list_tool_categories(_: object = Depends(get_current_user)):
    categories = tool_registry.get_categories()
    return {"categories": categories}


@router.get("/health")
async def list_tools_health(_: object = Depends(get_current_user)):
    tool_names = list(tool_registry.tools.keys())
    results = await asyncio.gather(*(tool_registry.health_check(name) for name in tool_names))
    return results


@router.get("/{tool_name}/health")
async def get_tool_health(tool_name: str, _: object = Depends(get_current_user)):
    result = await tool_registry.health_check(tool_name)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")
    return result


@router.get("/{tool_name}", response_model=ToolInfo)
async def get_tool(tool_name: str, _: object = Depends(get_current_user)):
    registered = tool_registry.tools.get(tool_name)
    if registered and registered.tool:
        schema = registered.tool.get_schema()
        return ToolInfo(
            name=schema["name"],
            description=schema["description"],
            type=getattr(registered.tool, "tool_type", "builtin"),
            status="active",
            parameters=schema.get("parameters", {}),
            category=registered.category,
            version=registered.version,
            health_status=registered.health_status,
            tags=registered.tags,
        )

    tool = await tool_repo.get_by_name(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

    return ToolInfo(
        name=tool.name,
        description=tool.description,
        type=getattr(tool, "type", getattr(tool, "tool_type", "builtin")),
        status=getattr(tool, "status", "active"),
        parameters=getattr(tool, "parameters_schema", {}) or {},
        category=getattr(tool, "category", "general"),
        version=getattr(tool, "version", "1.0.0"),
        health_status=getattr(tool, "health_status", "unknown"),
        tags=getattr(tool, "tags", []),
    )


@router.post("", response_model=ToolRegisterResponse)
async def register_tool(request: ToolRegisterRequest, current_user: object = Depends(get_current_user)):
    tool = DynamicTool(request.name, request.description, request.parameters_schema, request.template)
    tool_registry.register(tool)
    await tool_repo.upsert(
        name=request.name,
        description=request.description,
        tool_type=request.type,
        parameters_schema=request.parameters_schema,
        template=request.template,
        status="active",
    )
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} registered tool {request.name}")
    return ToolRegisterResponse(
        success=True,
        tool=ToolInfo(
            name=tool.name,
            description=tool.description,
            type=request.type,
            status="active",
            parameters=request.parameters_schema,
            category="general",
            version="1.0.0",
            health_status="unknown",
            tags=[],
        ),
    )


@router.post("/{tool_name}/execute")
async def execute_tool(tool_name: str, request: ToolExecuteRequest, current_user: object = Depends(get_current_user)):
    logger.info(f"User {getattr(current_user, 'id', 'unknown')} executing tool {tool_name}")
    result = await tool_registry.execute(tool_name, request.parameters)
    if not result.success:
        logger.warning(f"Tool {tool_name} execution failed: {result.error}")
        raise HTTPException(status_code=400, detail=result.error or "Tool execution failed")
    return result



