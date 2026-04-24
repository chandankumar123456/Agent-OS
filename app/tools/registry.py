from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from .base import BaseTool, ToolInput, ToolOutput
from .search import SearchTool, CalculatorTool, TextProcessorTool
from ..logs.logger import logger


@dataclass
class RegisteredTool:
    name: str
    description: str
    type: str
    tool: Optional[BaseTool]
    mcp_tool: bool = False


class MCPWrappedTool:
    """Wraps an MCP tool so it looks like a BaseTool to the executor."""

    def __init__(self, name: str, description: str, schema: Dict[str, Any]):
        self.name = name
        self.description = description
        self._schema = schema
        self.tool_type = "mcp"

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._schema,
        }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from ..mcp.client_manager import mcp_client_manager
        try:
            result = await mcp_client_manager.call_tool(self.name, tool_input.parameters)
            content = ""
            if hasattr(result, "content"):
                content = "\n".join(
                    str(c.text if hasattr(c, "text") else c)
                    for c in result.content
                )
            else:
                content = str(result)
            return ToolOutput(success=True, data={"output": content})
        except Exception as e:
            logger.error(f"MCP tool execution error: {e}")
            return ToolOutput(success=False, error=str(e))


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, RegisteredTool] = {}
        self._mcp_tools_registered = False
        self._register_default_tools()

    def _register_default_tools(self):
        self.register(SearchTool())
        self.register(CalculatorTool())
        self.register(TextProcessorTool())
        logger.info("Default tools registered")

    def register(self, tool: BaseTool):
        self.tools[tool.name] = RegisteredTool(
            name=tool.name,
            description=tool.description,
            type=getattr(tool, "tool_type", "builtin"),
            tool=tool,
            mcp_tool=False,
        )
        logger.info(f"Registered tool: {tool.name}")

    def register_mcp_tools(self, mcp_tools: List[Dict[str, Any]]):
        """Register tools discovered from MCP servers."""
        for tool_info in mcp_tools:
            name = tool_info["name"]
            self.tools[name] = RegisteredTool(
                name=name,
                description=tool_info.get("description", ""),
                type="mcp",
                tool=MCPWrappedTool(
                    name=name,
                    description=tool_info.get("description", ""),
                    schema=tool_info.get("input_schema", {}),
                ),
                mcp_tool=True,
            )
            logger.info(f"Registered MCP tool: {name}")
        self._mcp_tools_registered = True

    async def discover_mcp_tools(self) -> None:
        """Discover and register tools from connected MCP servers."""
        if self._mcp_tools_registered:
            return
        try:
            from ..mcp.client_manager import mcp_client_manager
            mcp_tools = await mcp_client_manager.list_tools()
            self.register_mcp_tools(mcp_tools)
        except Exception as e:
            logger.warning(f"MCP tool discovery failed (will retry later): {e}")

    def get(self, name: str) -> Optional[BaseTool]:
        registered = self.tools.get(name)
        return registered.tool if registered else None

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                **(registered.tool.get_schema() if registered.tool else {}),
                "type": registered.type,
                "status": "active",
            }
            for registered in self.tools.values()
        ]

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ToolOutput:
        registered = self.tools.get(tool_name)

        if not registered:
            return ToolOutput(
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        if registered.mcp_tool and registered.tool:
            tool_input = ToolInput(parameters=parameters)
            return await registered.tool.execute(tool_input)

        if not registered.tool:
            return ToolOutput(success=False, error=f"Tool '{tool_name}' has no implementation")

        try:
            tool_input = ToolInput(parameters=parameters)
            result = await registered.tool.execute(tool_input)
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return ToolOutput(success=False, error=str(e))


tool_registry = ToolRegistry()
