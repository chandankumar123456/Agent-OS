from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from ...tools.registry import tool_registry
from ...tools.base import BaseTool, ToolInput, ToolOutput
from ...api.deps import get_current_user
from ...memory.long_term import tool_repo

router = APIRouter(prefix="/tools", tags=["tools"])


def _is_admin(user: object) -> bool:
    return getattr(user, "role", "user") == "admin"


class ToolInfo(BaseModel):
    name: str
    description: str
    type: str
    status: str
    parameters: Dict[str, Any]


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


class DynamicTool(BaseTool):
    def __init__(self, name: str, description: str, parameters_schema: Dict[str, Any], template: Optional[str] = None):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.template = template
        self.tool_type = "custom"

    async def execute(self, tool_input: ToolInput):
        return ToolOutput(
            success=True,
            result={
                "tool": self.name,
                "parameters": tool_input.parameters,
                "template": self.template,
            },
        )


@router.get("", response_model=List[ToolInfo])
async def list_tools(_: object = Depends(get_current_user)):
    tools = await tool_repo.list_all()
    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            type=getattr(t, "type", getattr(t, "tool_type", "unknown")),
            status=getattr(t, "status", "active"),
            parameters=getattr(t, "parameters_schema", {}) or {},
        )
        for t in tools
    ]


@router.get("/{tool_name}", response_model=ToolInfo)
async def get_tool(tool_name: str, _: object = Depends(get_current_user)):
    tool = await tool_repo.get_by_name(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

    return ToolInfo(
        name=tool.name,
        description=tool.description,
        type=getattr(tool, "type", getattr(tool, "tool_type", "builtin")),
        status=getattr(tool, "status", "active"),
        parameters=getattr(tool, "parameters_schema", {}) or {},
    )


@router.post("", response_model=ToolRegisterResponse)
async def register_tool(request: ToolRegisterRequest, current_user: object = Depends(get_current_user)):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Forbidden")
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
    return ToolRegisterResponse(
        success=True,
        tool=ToolInfo(
            name=tool.name,
            description=tool.description,
            type=request.type,
            status="active",
            parameters=request.parameters_schema,
        ),
    )


@router.post("/{tool_name}/execute")
async def execute_tool(tool_name: str, request: ToolExecuteRequest, _: object = Depends(get_current_user)):
    result = await tool_registry.execute(tool_name, request.parameters)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Tool execution failed")
    return result
