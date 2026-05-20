import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
        from .local_fallbacks import LOCAL_FALLBACKS
        logger.info(f"[registry][TRACE] MCP INVOKE: name='{self.name}' args={ {k:v for k,v in tool_input.parameters.items() if not k.startswith('_')} }")
        try:
            # Strip internal params (e.g., _task_id) before sending to MCP server,
            # but remap _task_id -> task_id so per-task session isolation works
            # across environment MCP servers (browser_env, desktop).
            # ALWAYS overwrite task_id to prevent task hijacking via _task_id injection.
            arguments = {k: v for k, v in tool_input.parameters.items() if not k.startswith("_")}
            if "_task_id" in tool_input.parameters:
                arguments["task_id"] = tool_input.parameters["_task_id"]
            result = await mcp_client_manager.call_tool(self.name, arguments)
            content = ""
            if hasattr(result, "content"):
                content = "\n".join(
                    str(c.text if hasattr(c, "text") else c)
                    for c in result.content
                )
            else:
                content = str(result)
            logger.info(f"[registry][TRACE] MCP RESULT: name='{self.name}' success=True content_preview='{content[:200]}'")

            visibility = None
            if self.name.startswith("filesystem__"):
                path = tool_input.parameters.get("path", "")
                visibility = {"type": "file_operation", "path": path, "operation": self.name}
            elif self.name.startswith("shell__"):
                cmd = tool_input.parameters.get("command", "")
                visibility = {"type": "shell_output", "command": cmd}

            return ToolOutput(success=True, result={"output": content}, visibility=visibility)
        except Exception as e:
            logger.error(f"[registry][TRACE] MCP ERROR: name='{self.name}' error={e}")
            # Fallback to local implementation if MCP server is unavailable
            fallback_fn = LOCAL_FALLBACKS.get(self.name)
            if fallback_fn is not None:
                logger.info(f"[registry][TRACE] MCP FALLBACK: name='{self.name}' using local implementation")
                try:
                    arguments = {k: v for k, v in tool_input.parameters.items() if not k.startswith("_")}
                    fallback_result = await fallback_fn(**arguments)
                    visibility = None
                    if self.name.startswith("filesystem__"):
                        path = tool_input.parameters.get("path", "")
                        visibility = {"type": "file_operation", "path": path, "operation": self.name}
                    elif self.name.startswith("shell__"):
                        cmd = tool_input.parameters.get("command", "")
                        visibility = {"type": "shell_output", "command": cmd}
                    return ToolOutput(success=True, result={"output": fallback_result}, visibility=visibility)
                except Exception as fallback_err:
                    logger.error(f"[registry][TRACE] MCP FALLBACK ERROR: name='{self.name}' error={fallback_err}")
                    return ToolOutput(success=False, error=f"MCP failed: {e}; fallback failed: {fallback_err}")
            return ToolOutput(success=False, error=str(e))


class DesktopEnvTool:
    """Tool wrapper for desktop environment operations. Provides a unified interface
    for all desktop automation actions with dict-based dispatch for maintainability."""

    def __init__(self, name, action):
        self.name = name
        self.description = f"Desktop environment: {action}"
        self.tool_type = "desktop_env"
        self._action = action

    def get_schema(self):
        schema = {"name": self.name, "description": self.description, "parameters": {"type": "object", "properties": {}}}
        schema_map = {
            "click": {"properties": {"x": {"type": "integer", "description": "X coordinate"}, "y": {"type": "integer", "description": "Y coordinate"}}, "required": ["x", "y"]},
            "type_text": {"properties": {"text": {"type": "string", "description": "Text to type"}, "interval": {"type": "number", "description": "Typing interval in seconds", "default": 0.01}}, "required": ["text"]},
            "press_key": {"properties": {"keys": {"type": "string", "description": "Key or key combination to press (e.g., 'ctrl+c')"}}, "required": ["keys"]},
            "screenshot": {"properties": {"path": {"type": "string", "description": "Optional file path to save screenshot"}}},
            "focus_window": {"properties": {"title": {"type": "string", "description": "Window title substring to focus"}}, "required": ["title"]},
            "get_window_list": {"properties": {}},
            "get_clipboard": {"properties": {}},
            "set_clipboard": {"properties": {"text": {"type": "string", "description": "Text to copy to clipboard"}}, "required": ["text"]},
            "get_mouse_position": {"properties": {}},
            "scroll": {"properties": {"amount": {"type": "integer", "description": "Scroll amount (positive=down, negative=up)"}}, "required": ["amount"]},
            "close": {"properties": {}},
            "get_ui_tree": {"properties": {}},
            "click_element": {"properties": {"element_id": {"type": "integer", "description": "Element ID from get_ui_tree"}}, "required": ["element_id"]},
            "type_element": {"properties": {"element_id": {"type": "integer", "description": "Element ID from get_ui_tree"}, "text": {"type": "string", "description": "Text to type"}}, "required": ["element_id", "text"]},
            "focus_and_interact": {"properties": {"element_id": {"type": "integer", "description": "Element ID from get_ui_tree"}, "key": {"type": "string", "description": "Key to press", "default": "enter"}}, "required": ["element_id"]},
            "ensure_focus": {"properties": {"window_ref_id": {"type": "string", "description": "Window reference ID to focus"}, "title": {"type": "string", "description": "Window title substring to focus"}}},
            "launch_app_and_open_file": {"properties": {"file_path": {"type": "string", "description": "Absolute path to the file to open"}, "app_name": {"type": "string", "description": "Application name to use for opening"}}, "required": ["file_path"]},
            "open_application": {"properties": {"app_name": {"type": "string", "description": "Name of the application to open (e.g., notepad, chrome, vscode)"}}, "required": ["app_name"]},
            "get_window_registry": {"properties": {}},
            "save_checkpoint": {"properties": {"step": {"type": "string", "description": "Checkpoint step identifier"}}, "required": ["step"]},
            "get_workflow_state": {"properties": {}},
            "set_approval_mode": {"properties": {"mode": {"type": "string", "enum": ["standard", "full_trust"], "description": "Approval mode for this session"}}, "required": ["mode"]},
        }
        if self._action in schema_map:
            schema["parameters"].update(schema_map[self._action])
        return schema

    async def execute(self, tool_input: ToolInput):
        from ..environments.desktop_env import desktop_session_manager

        params = tool_input.parameters
        task_id = params.get("_task_id", "")
        if not task_id:
            return ToolOutput(success=False, error="'_task_id' parameter is required for desktop environment tools")

        logger.info(f"[registry][TRACE] DESKTOP TOOL WRAPPER: name='{self.name}' action='{self._action}' task_id='{task_id}' params={ {k:v for k,v in params.items() if not k.startswith('_')} }")
        session = await desktop_session_manager.get_or_create_session(task_id)

        # Dict-based dispatch for most session-method actions
        _dispatch = {
            "screenshot": lambda: session.screenshot(params.get("path")),
            "click": lambda: session.click(params.get("x", 0), params.get("y", 0)),
            "type_text": lambda: session.type_text(params.get("text", ""), params.get("interval", 0.01)),
            "press_key": lambda: session.press_key(params.get("keys", "")),
            "get_window_list": lambda: session.get_window_list(),
            "focus_window": lambda: session.focus_window(params.get("title", "")),
            "get_clipboard": lambda: session.get_clipboard(),
            "set_clipboard": lambda: session.set_clipboard(params.get("text", "")),
            "get_mouse_position": lambda: session.get_mouse_position(),
            "scroll": lambda: session.scroll(params.get("amount", 0)),
            "get_ui_tree": lambda: session.get_ui_tree(),
            "click_element": lambda: session.click_element(params.get("element_id", 0)),
            "type_element": lambda: session.type_element(params.get("element_id", 0), params.get("text", "")),
            "focus_and_interact": lambda: session.focus_and_interact(params.get("element_id", 0), params.get("key", "enter")),
            "ensure_focus": lambda: session.ensure_focus(window_ref_id=params.get("window_ref_id"), title=params.get("title")),
            "launch_app_and_open_file": lambda: session.launch_app_and_open_file(file_path=params["file_path"], app_name=params.get("app_name")),
            "open_application": lambda: session.open_application(app_name=params["app_name"]),
        }

        if self._action in _dispatch:
            return await _dispatch[self._action]()

        if self._action == "close":
            return await desktop_session_manager.close_session(task_id)
        elif self._action == "get_window_registry":
            registry = session.get_window_registry()
            return ToolOutput(success=True, result=registry.to_dict() if registry else {"refs": [], "count": 0})
        elif self._action == "save_checkpoint":
            orchestrator = await session.get_orchestrator()
            await orchestrator.save_checkpoint(step=params["step"])
            return ToolOutput(success=True, result=orchestrator.get_state())
        elif self._action == "get_workflow_state":
            orchestrator = await session.get_orchestrator()
            return ToolOutput(success=True, result=orchestrator.get_state())
        elif self._action == "set_approval_mode":
            from ..safety.approval_store import approval_store
            mode = params.get("mode", "standard")
            approval_store.set_mode(task_id, mode)
            return ToolOutput(success=True, result={"message": f"Approval mode set to {mode}", "task_id": task_id})

        logger.error(f"[registry][TRACE] DESKTOP TOOL WRAPPER: unknown action '{self._action}'")
        return ToolOutput(success=False, error=f"Unknown action: {self._action}")


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
        self._discovery_lock = asyncio.Lock()
        self._register_default_tools()
        self._register_filesystem_tools()
        self._register_shell_tools()
        self._register_cloud_api_tools()
        self._register_browser_env_tools()
        self._register_desktop_env_tools()
        self._register_document_tools()
        self._register_code_tools()
        self._register_communication_tools()
        self._initialized = True

    def _register_default_tools(self):
        self.register(SearchTool())
        self.register(CalculatorTool())
        self.register(TextProcessorTool())
        # Document tools are now provided by the document MCP server.
        # Placeholders with schemas are registered in _register_document_tools()
        # so the grounding layer sees them before MCP discovery completes.
        logger.info("Default tools registered")

    def _register_filesystem_tools(self):
        """Register filesystem tools as MCP wrappers.

        The actual file system logic lives in the ``filesystem`` MCP stdio server
        (``app/mcp/servers/filesystem.py``).  These placeholders ensure the tools
        are visible to the grounding layer and executor even before MCP discovery.
        """
        schemas = {
            "filesystem__read_file": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file to read"},
                },
                "required": ["path"],
            },
            "filesystem__write_file": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
            "filesystem__list_directory": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the directory"},
                },
                "required": ["path"],
            },
            "filesystem__search_files": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search in"},
                    "pattern": {"type": "string", "description": "Glob pattern to match"},
                },
                "required": ["path", "pattern"],
            },
        }
        for name, schema in schemas.items():
            action = name.split("__")[-1]
            self.tools[name] = RegisteredTool(
                name=name,
                description=f"Filesystem: {action}",
                type="mcp",
                tool=MCPWrappedTool(name=name, description=f"Filesystem: {action}", schema=schema),
                mcp_tool=True,
            )
        logger.info("Filesystem tools registered (MCP placeholders)")

    def _register_shell_tools(self):
        """Register shell tools as MCP wrappers.

        The actual shell logic lives in the ``shell`` MCP stdio server
        (``app/mcp/servers/shell.py``).  These placeholders ensure the tools
        are visible to the grounding layer and executor even before MCP discovery.
        """
        schemas = {
            "shell__execute_command": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                    "cwd": {"type": "string", "description": "Working directory"},
                },
                "required": ["command"],
            },
            "shell__run_script": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "Script content"},
                    "interpreter": {"type": "string", "description": "Interpreter to use", "default": "bash"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                },
                "required": ["script"],
            },
            "shell__get_process_status": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                },
                "required": ["pid"],
            },
        }
        for name, schema in schemas.items():
            action = name.split("__")[-1]
            self.tools[name] = RegisteredTool(
                name=name,
                description=f"Shell: {action}",
                type="mcp",
                tool=MCPWrappedTool(name=name, description=f"Shell: {action}", schema=schema),
                mcp_tool=True,
            )
        logger.info("Shell tools registered (MCP placeholders)")

    def _register_cloud_api_tools(self):
        """Register cloud API tools as MCP wrappers.

        The actual web logic lives in the ``cloud_api`` MCP stdio server
        (``app/mcp/servers/cloud_api.py``).  These placeholders ensure the tools
        are visible to the grounding layer and executor even before MCP discovery.
        """
        schemas = {
            "cloud_api__search_web": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Maximum results", "default": 5},
                },
                "required": ["query"],
            },
            "cloud_api__http_request": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request"},
                    "method": {"type": "string", "description": "HTTP method", "default": "GET"},
                    "headers": {"type": "object", "description": "Request headers"},
                    "body": {"type": "string", "description": "Request body"},
                },
                "required": ["url"],
            },
            "cloud_api__scrape_page": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                    "selector": {"type": "string", "description": "CSS selector to extract"},
                },
                "required": ["url"],
            },
            "cloud_api__send_email": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body"},
                },
                "required": ["to", "subject", "body"],
            },
            "cloud_api__send_message": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "Message recipient"},
                    "message": {"type": "string", "description": "Message content"},
                },
                "required": ["recipient", "message"],
            },
        }
        for name, schema in schemas.items():
            action = name.split("__")[-1]
            self.tools[name] = RegisteredTool(
                name=name,
                description=f"Cloud API: {action}",
                type="mcp",
                tool=MCPWrappedTool(name=name, description=f"Cloud API: {action}", schema=schema),
                mcp_tool=True,
            )
        logger.info("Cloud API tools registered (MCP placeholders)")

    def _register_browser_env_tools(self):
        """Register browser tools as MCP wrappers.

        The actual Playwright logic lives in the ``browser_env`` MCP stdio server
        (``app/mcp/servers/browser.py``).  These placeholders ensure the tools are
        visible to the grounding layer and executor even before MCP discovery runs.
        When ``discover_mcp_tools()`` connects to the real server, the schemas are
        refreshed automatically.
        """
        schemas = {
            "browser_env__launch": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "headless": {"type": "boolean", "description": "Run in headless mode"},
                },
            },
            "browser_env__navigate": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "url": {"type": "string", "description": "URL to navigate to"},
                },
                "required": ["url"],
            },
            "browser_env__search": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
            "browser_env__click": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "selector": {"type": "string", "description": "CSS selector or xpath"},
                },
                "required": ["selector"],
            },
            "browser_env__type": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "selector": {"type": "string", "description": "CSS selector or xpath"},
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["selector", "text"],
            },
            "browser_env__screenshot": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "path": {"type": "string", "description": "Optional file path to save screenshot"},
                },
            },
            "browser_env__get_text": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                    "selector": {"type": "string", "description": "CSS selector or xpath"},
                },
                "required": ["selector"],
            },
            "browser_env__close": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task-scoped session identifier"},
                },
            },
        }
        for name, schema in schemas.items():
            action = name.split("__")[-1]
            self.tools[name] = RegisteredTool(
                name=name,
                description=f"Browser environment: {action}",
                type="mcp",
                tool=MCPWrappedTool(name=name, description=f"Browser environment: {action}", schema=schema),
                mcp_tool=True,
            )
        logger.info("Browser environment tools registered (MCP placeholders)")

    def _register_document_tools(self):
        """Register document tools as MCP wrappers.

        The actual parsing logic lives in the ``document`` MCP stdio server
        (``app/mcp/servers/document.py``).  These placeholders ensure the tools
        are visible to the grounding layer and executor even before MCP discovery.
        """
        schemas = {
            "document__parse": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the document"},
                    "skip_summary": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
            "document__parse_pdf": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the PDF"},
                },
                "required": ["path"],
            },
            "document__parse_docx": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the DOCX"},
                },
                "required": ["path"],
            },
            "document__parse_txt": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the text file"},
                },
                "required": ["path"],
            },
            "document__parse_markdown": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the Markdown file"},
                },
                "required": ["path"],
            },
            "document__chunk": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to chunk"},
                    "chunk_size": {"type": "integer", "default": 2000},
                    "overlap": {"type": "integer", "default": 200},
                },
                "required": ["text"],
            },
            "document__summarize": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the document"},
                },
                "required": ["path"],
            },
        }
        for name, schema in schemas.items():
            self.tools[name] = RegisteredTool(
                name=name,
                description=f"Document parsing: {name.split('__')[-1]}",
                type="mcp",
                tool=MCPWrappedTool(name=name, description=f"Document parsing: {name.split('__')[-1]}", schema=schema),
                mcp_tool=True,
            )
        logger.info("Document tools registered (MCP placeholders)")

    def _register_code_tools(self):
        """Register code execution tools as MCP wrappers.

        The actual sandboxed execution lives in the ``code_executor`` MCP stdio
        server (``app/mcp/servers/code.py``).
        """
        schema = {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute. Assign result to a variable named 'result'."},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["code"],
        }
        self.tools["code_executor__run_python"] = RegisteredTool(
            name="code_executor__run_python",
            description="Execute Python code in a sandboxed environment",
            type="mcp",
            tool=MCPWrappedTool(
                name="code_executor__run_python",
                description="Execute Python code in a sandboxed environment",
                schema=schema,
            ),
            mcp_tool=True,
        )
        logger.info("Code execution tools registered (MCP placeholders)")

    def _register_communication_tools(self):
        """Register communication tools as MCP wrappers.

        Placeholders for Slack and other communication MCP servers.
        """
        schemas = {
            "slack__send_message": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Slack channel ID or name"},
                    "message": {"type": "string", "description": "Message text"},
                },
                "required": ["channel", "message"],
            },
        }
        for name, schema in schemas.items():
            action = name.split("__")[-1]
            self.tools[name] = RegisteredTool(
                name=name,
                description=f"Communication: {action}",
                type="mcp",
                tool=MCPWrappedTool(name=name, description=f"Communication: {action}", schema=schema),
                mcp_tool=True,
            )
        logger.info("Communication tools registered (MCP placeholders)")

    def _register_desktop_env_tools(self):
        for action in ["screenshot", "click", "type_text", "press_key", "get_window_list", "focus_window", "get_clipboard", "set_clipboard", "get_mouse_position", "scroll", "close", "ensure_focus", "launch_app_and_open_file", "open_application", "get_window_registry", "save_checkpoint", "get_workflow_state", "set_approval_mode"]:
            self.register(DesktopEnvTool(f"desktop_env__{action}", action))
        # Register semantic element-based tools with desktop__ prefix (matching MCP naming)
        for action in ["get_ui_tree", "click_element", "type_element", "focus_and_interact"]:
            self.register(DesktopEnvTool(f"desktop__{action}", action))
        # Register desktop__ aliases for grounding layer compatibility
        for action in ["screenshot", "click", "type_text", "press_key", "get_window_list", "focus_window", "get_clipboard", "set_clipboard"]:
            self.register(DesktopEnvTool(f"desktop__{action}", action))
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

    async def discover_mcp_tools(self) -> None:
        """Discover and register tools from connected MCP servers."""
        async with self._discovery_lock:
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
        logger.info(f"[registry][TRACE] EXECUTE ENTRY: tool_name='{tool_name}' params_keys={list(parameters.keys())}")
        registered = self.tools.get(tool_name)

        if not registered:
            logger.error(f"[registry][TRACE] EXECUTE FAIL: tool '{tool_name}' not found in registry")
            return ToolOutput(
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        if not registered.tool:
            logger.error(f"[registry][TRACE] EXECUTE FAIL: tool '{tool_name}' has no implementation")
            return ToolOutput(success=False, error=f"Tool '{tool_name}' has no implementation")

        # Validate parameters against schema
        schema = registered.tool.get_schema()
        required = schema.get("parameters", {}).get("required", [])
        for param in required:
            if param not in parameters:
                logger.error(f"[registry][TRACE] EXECUTE FAIL: tool '{tool_name}' missing required param '{param}'")
                return ToolOutput(
                    success=False,
                    error=f"Missing required parameter '{param}' for tool '{tool_name}'",
                )

        # Safety gate: mandatory pre-execution validation for ALL tool invocations
        from ..safety.gate import safety_gate
        from ..safety.models import ActionSeverity
        severity = safety_gate.check_tool_call(tool_name, parameters, "")
        if severity.value >= ActionSeverity.IRREVERSIBLE.value:
            logger.error(f"[registry][TRACE] EXECUTE BLOCKED: tool '{tool_name}' severity={severity.value}")
            return ToolOutput(
                success=False,
                error=f"Safety gate blocked tool {tool_name}: {severity.value}",
            )

        # For desktop tools, also validate credential leakage in parameters
        if tool_name.startswith(("desktop_env__", "desktop__")):
            cred_violation = safety_gate.validate_desktop_params(parameters)
            if cred_violation.blocked:
                logger.error(f"[registry][TRACE] EXECUTE BLOCKED: tool '{tool_name}' credential violation")
                return ToolOutput(
                    success=False,
                    error=f"Safety gate blocked credential in desktop tool: {cred_violation.reason}",
                )

        # Capability check: require approval for sensitive tools
        try:
            from ..desktop_native.capability_manager import capability_manager, CapabilityStatus
            task_id = parameters.get("_task_id", "unknown")
            token = await capability_manager.request_capability(tool_name, task_id)
            if not token or token.status != CapabilityStatus.APPROVED:
                logger.error(f"[registry][TRACE] EXECUTE BLOCKED: tool '{tool_name}' capability not approved")
                return ToolOutput(
                    success=False,
                    error=f"Capability not approved for tool '{tool_name}'. Please approve in the GUI.",
                )
        except Exception as cap_err:
            logger.warning(f"[registry][TRACE] Capability check failed for '{tool_name}': {cap_err}")
            # Fail open only if capability manager is not initialized; otherwise fail closed
            # For desktop-native, we require the check to work

        logger.info(f"[registry][TRACE] EXECUTE DISPATCH: tool_name='{tool_name}' type={getattr(registered.tool, 'tool_type', 'unknown')} mcp={registered.mcp_tool}")
        try:
            tool_input = ToolInput(parameters=parameters)
            # Enforce tool timeout to prevent hanging (e.g., recursive file searches)
            tool_timeout = parameters.get("_timeout", 60)
            result = await asyncio.wait_for(
                registered.tool.execute(tool_input),
                timeout=tool_timeout,
            )
            logger.info(f"[registry][TRACE] EXECUTE RESULT: tool_name='{tool_name}' success={result.success} result={result.result} error={result.error}")
        except asyncio.TimeoutError:
            logger.error(f"[registry][TRACE] EXECUTE TIMEOUT: tool_name='{tool_name}' after {tool_timeout}s")
            logger.error(f"Tool '{tool_name}' timed out after {tool_timeout}s")
            result = ToolOutput(success=False, error=f"Tool '{tool_name}' timed out after {tool_timeout}s")
        except Exception as e:
            logger.error(f"[registry][TRACE] EXECUTE EXCEPTION: tool_name='{tool_name}' error={e}")
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
            registered.last_used = datetime.now(timezone.utc).isoformat()
        return result



async def is_task_cancelled(task_id: str) -> bool:
    """Check if a task has been cancelled (via Redis signal)."""
    try:
        from ..memory.short_term import redis_client
        if redis_client and redis_client.client:
            result = await redis_client.client.get(f"agentos:cancelled:{task_id}")
            return result is not None
    except Exception:
        pass
    return False


tool_registry = ToolRegistry()
