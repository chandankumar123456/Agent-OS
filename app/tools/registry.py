import asyncio
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
            # Strip internal params (e.g., _task_id) before sending to MCP server
            arguments = {k: v for k, v in tool_input.parameters.items() if not k.startswith("_")}
            result = await mcp_client_manager.call_tool(self.name, arguments)
            content = ""
            if hasattr(result, "content"):
                content = "\n".join(
                    str(c.text if hasattr(c, "text") else c)
                    for c in result.content
                )
            else:
                content = str(result)

            visibility = None
            if self.name.startswith("filesystem__"):
                path = tool_input.parameters.get("path", "")
                visibility = {"type": "file_operation", "path": path, "operation": self.name}
            elif self.name.startswith("shell__"):
                cmd = tool_input.parameters.get("command", "")
                visibility = {"type": "shell_output", "command": cmd}

            return ToolOutput(success=True, result={"output": content}, visibility=visibility)
        except Exception as e:
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
        self._discovery_lock = asyncio.Lock()
        self._register_default_tools()
        self._register_browser_env_tools()
        self._register_desktop_env_tools()
        self._initialized = True
        # Initialize dynamic tool builder
        try:
            from .builder import init_dynamic_tool_factory
            init_dynamic_tool_factory(self)
        except Exception as e:
            logger.warning(f"Dynamic tool factory init failed: {e}")

    def _register_default_tools(self):
        self.register(SearchTool())
        self.register(CalculatorTool())
        self.register(TextProcessorTool())
        try:
            from ..pipelines.document_ingestion import DocumentParseTool
            self.register(DocumentParseTool())
        except Exception as e:
            logger.warning(f"Could not register DocumentParseTool at startup: {e}")
        logger.info("Default tools registered")

    def _register_browser_env_tools(self):
        from ..environments.browser_env import browser_session_manager

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
                task_id = params.get("_task_id", "default")
                session = await browser_session_manager.get_or_create_session(task_id)

                if self._action == "launch":
                    return await session.launch(params.get("headless", False))
                elif self._action == "navigate":
                    url = params.get("url")
                    if not url:
                        return ToolOutput(success=False, error="Missing required parameter 'url' for browser_env__navigate")
                    return await session.navigate(url)
                elif self._action == "search":
                    return await session.search(params.get("query"))
                elif self._action == "click":
                    return await session.click(params.get("selector"))
                elif self._action == "type":
                    return await session.type_text(params.get("selector"), params.get("text"))
                elif self._action == "screenshot":
                    return await session.screenshot(params.get("path"))
                elif self._action == "get_text":
                    return await session.get_text(params.get("selector"))
                elif self._action == "close":
                    return await browser_session_manager.close_session(task_id)
                return ToolOutput(success=False, error=f"Unknown action: {self._action}")

        for action in ["launch", "navigate", "search", "click", "type", "screenshot", "get_text", "close"]:
            self.register(BrowserEnvTool(f"browser_env__{action}", action))
        logger.info("Browser environment tools registered")

    def _register_desktop_env_tools(self):
        from ..environments.desktop_env import desktop_session_manager

        class DesktopEnvTool:
            def __init__(self, name, action):
                self.name = name
                self.description = f"Desktop environment: {action}"
                self.tool_type = "desktop_env"
                self._action = action

            def get_schema(self):
                return {"name": self.name, "description": self.description, "parameters": {}}

            async def execute(self, tool_input: ToolInput):
                params = tool_input.parameters
                task_id = params.get("_task_id", "default")
                session = await desktop_session_manager.get_or_create_session(task_id)

                if self._action == "screenshot":
                    return await session.screenshot(params.get("path"))
                elif self._action == "click":
                    return await session.click(params.get("x", 0), params.get("y", 0))
                elif self._action == "type_text":
                    return await session.type_text(params.get("text", ""), params.get("interval", 0.01))
                elif self._action == "press_key":
                    return await session.press_key(params.get("keys", ""))
                elif self._action == "get_window_list":
                    return await session.get_window_list()
                elif self._action == "focus_window":
                    return await session.focus_window(params.get("title", ""))
                elif self._action == "get_clipboard":
                    return await session.get_clipboard()
                elif self._action == "set_clipboard":
                    return await session.set_clipboard(params.get("text", ""))
                elif self._action == "get_mouse_position":
                    return await session.get_mouse_position()
                elif self._action == "scroll":
                    return await session.scroll(params.get("amount", 0))
                elif self._action == "close":
                    return await desktop_session_manager.close_session(task_id)
                return ToolOutput(success=False, error=f"Unknown action: {self._action}")

        for action in ["screenshot", "click", "type_text", "press_key", "get_window_list", "focus_window", "get_clipboard", "set_clipboard", "get_mouse_position", "scroll", "close"]:
            self.register(DesktopEnvTool(f"desktop_env__{action}", action))
        logger.info("Desktop environment tools registered")

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
        async with self._discovery_lock:
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
        if registered:
            return registered.tool
        # Try dynamic build
        try:
            from .builder import dynamic_tool_factory
            if dynamic_tool_factory:
                # Fire-and-forget async build (sync wrapper)
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(dynamic_tool_factory.ensure_tool(name))
                except RuntimeError:
                    pass
                # Re-check after giving async a moment
                registered = self.tools.get(name)
                if registered:
                    return registered.tool
        except Exception as e:
            logger.debug(f"Dynamic tool build attempt failed for {name}: {e}")
        return None

    def get_by_prefix(self, prefix: str) -> List[Dict[str, Any]]:
        """Return all tools whose name starts with the given prefix."""
        return [
            {
                **(registered.tool.get_schema() if registered.tool else {}),
                "type": registered.type,
                "status": "active",
            }
            for registered in self.tools.values()
            if registered.name.startswith(prefix)
        ]

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
        import asyncio
        registered = self.tools.get(tool_name)

        if not registered:
            return ToolOutput(
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        if not registered.tool:
            return ToolOutput(success=False, error=f"Tool '{tool_name}' has no implementation")

        try:
            tool_input = ToolInput(parameters=parameters)
            # Enforce tool timeout to prevent hanging (e.g., recursive file searches)
            tool_timeout = parameters.get("_timeout", 60)
            result = await asyncio.wait_for(
                registered.tool.execute(tool_input),
                timeout=tool_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(f"Tool '{tool_name}' timed out after {tool_timeout}s")
            result = ToolOutput(success=False, error=f"Tool '{tool_name}' timed out after {tool_timeout}s")
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            result = ToolOutput(success=False, error=str(e))

        # SINGLE EMISSION POINT
        try:
            from ..observability.bus import observability_bus
            from ..observability.models import ObservabilityEventType
            task_id = parameters.get("_task_id", "unknown")
            await observability_bus.emit_safe(
                ObservabilityEventType.TOOL_RESULT,
                task_id=task_id,
                payload={
                    "tool_name": tool_name,
                    "success": result.success,
                    "result": result.result,
                    "visibility": result.visibility,
                    "error": result.error,
                },
                source="tool_registry",
            )
        except Exception as e:
            logger.warning(f"Failed to emit tool result visibility: {e}")

        if result.success:
            registered.use_count += 1
            registered.last_used = datetime.utcnow().isoformat()
        return result


tool_registry = ToolRegistry()
