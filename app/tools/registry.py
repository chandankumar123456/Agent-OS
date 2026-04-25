from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
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
    category: str = "general"
    version: str = "1.0.0"
    health_status: str = "unknown"
    use_count: int = 0
    tags: List[str] = field(default_factory=list)
    last_used: Optional[str] = None


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
            return ToolOutput(success=True, result={"output": content})
        except Exception as e:
            logger.error(f"MCP tool execution error: {e}")
            return ToolOutput(success=False, error=str(e))


class ToolRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.tools: Dict[str, RegisteredTool] = {}
        self._mcp_tools_registered = False
        self._register_default_tools()
        self._register_browser_env_tools()
        self._initialized = True

    def _register_default_tools(self):
        self.register(SearchTool())
        self.register(CalculatorTool())
        self.register(TextProcessorTool())
        logger.info("Default tools registered")

    def _register_browser_env_tools(self):
        from ..environments.browser_env import browser_environment

        class BrowserEnvTool:
            def __init__(self, name, action):
                self.name = name
                self.description = f"Browser environment: {action}"
                self.tool_type = "browser_env"
                self._action = action

            def get_schema(self):
                return {"name": self.name, "description": self.description, "parameters": {}}

            async def execute(self, tool_input: ToolInput):
                params = tool_input.parameters
                if self._action == "launch":
                    return await browser_environment.launch(params.get("url"), params.get("headless", False))
                elif self._action == "navigate":
                    return await browser_environment.navigate(params.get("url"))
                elif self._action == "search":
                    return await browser_environment.search(params.get("query"))
                elif self._action == "click":
                    return await browser_environment.click(params.get("selector"))
                elif self._action == "type":
                    return await browser_environment.type_text(params.get("selector"), params.get("text"))
                elif self._action == "screenshot":
                    return await browser_environment.screenshot(params.get("path"))
                elif self._action == "get_text":
                    return await browser_environment.get_text(params.get("selector"))
                elif self._action == "close":
                    return await browser_environment.close()
                return ToolOutput(success=False, error=f"Unknown action: {self._action}")

        for action in ["launch", "navigate", "search", "click", "type", "screenshot", "get_text", "close"]:
            self.register(BrowserEnvTool(f"browser_env__{action}", action))
        logger.info("Browser environment tools registered")

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
        if not mcp_tools:
            logger.warning("No MCP tools to register")
            return
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
                "category": registered.category,
                "version": registered.version,
                "health_status": registered.health_status,
                "tags": registered.tags,
                "use_count": registered.use_count,
                "last_used": registered.last_used,
            }
            for registered in self.tools.values()
        ]

    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [tool for tool in self.list_tools() if tool.get("category") == category]

    def get_categories(self) -> List[str]:
        return sorted({t.category for t in self.tools.values()})

    async def health_check(self, tool_name: str) -> Dict[str, str]:
        registered = self.tools.get(tool_name)
        if not registered:
            return {"name": tool_name, "status": "not_found"}
        try:
            result = await self.execute(tool_name, {})
            if result.success:
                registered.health_status = "healthy"
            else:
                registered.health_status = "unhealthy"
        except Exception as e:
            logger.error(f"Health check failed for {tool_name}: {e}")
            registered.health_status = "unhealthy"
        return {"name": tool_name, "status": registered.health_status}

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
            result = await registered.tool.execute(tool_input)
            if result.success:
                registered.use_count += 1
                registered.last_used = datetime.utcnow().isoformat()
            return result

        if not registered.tool:
            return ToolOutput(success=False, error=f"Tool '{tool_name}' has no implementation")

        try:
            tool_input = ToolInput(parameters=parameters)
            result = await registered.tool.execute(tool_input)
            if result.success:
                registered.use_count += 1
                registered.last_used = datetime.utcnow().isoformat()
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return ToolOutput(success=False, error=str(e))


tool_registry = ToolRegistry()
