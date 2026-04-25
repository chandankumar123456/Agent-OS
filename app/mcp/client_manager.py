"""MCP Client Manager — manages connections to MCP servers and routes tool calls."""
import asyncio
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from ..logs.logger import logger


@dataclass
class ServerConnection:
    name: str
    session: ClientSession
    tools: List[Dict[str, Any]] = field(default_factory=list)
    transport: str = "stdio"  # or "http"


class MCPClientManager:
    """Manages connections to multiple MCP servers and provides unified tool access.

    Usage:
        manager = MCPClientManager()
        await manager.connect_stdio("filesystem", "python", ["-m", "app.mcp.servers.filesystem"])
        tools = await manager.list_tools()
        result = await manager.call_tool("filesystem__read_file", {"path": "/tmp/test.txt"})
    """

    def __init__(self):
        self.connections: Dict[str, ServerConnection] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._exit_stacks: Dict[str, AsyncExitStack] = {}

    # ── Connection management ──────────────────────────────────────────

    async def connect_stdio(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ServerConnection:
        """Connect to an MCP server via stdio transport."""
        if name in self.connections:
            logger.warning(f"MCP server '{name}' already connected")
            return self.connections[name]

        logger.info(f"Connecting to MCP server '{name}' via stdio: {command} {args}")
        params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )

        exit_stack = AsyncExitStack()
        try:
            # Enter stdio_client context
            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(params)
            )
            # Enter ClientSession context
            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            # Initialize with timeout to avoid hanging on Windows
            await asyncio.wait_for(session.initialize(), timeout=10.0)

            conn = ServerConnection(name=name, session=session, transport="stdio")
            self.connections[name] = conn
            self._exit_stacks[name] = exit_stack

            # Discover tools
            tools_resp = await session.list_tools()
            conn.tools = [
                {
                    "name": self._tool_name(name, t.name),
                    "original_name": t.name,
                    "server": name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                }
                for t in (tools_resp.tools if hasattr(tools_resp, "tools") else [])
            ]
            for tool in conn.tools:
                self._tool_to_server[tool["name"]] = name

            logger.info(f"MCP server '{name}' connected with {len(conn.tools)} tools")
            return conn
        except asyncio.TimeoutError:
            await exit_stack.aclose()
            raise RuntimeError(f"MCP server '{name}' initialization timed out")
        except Exception:
            await exit_stack.aclose()
            raise

    async def connect_http(self, name: str, url: str) -> ServerConnection:
        """Connect to an MCP server via HTTP/SSE transport.

        Not yet implemented — placeholder for future HTTP transport support.
        """
        raise NotImplementedError("HTTP transport not yet implemented")

    async def disconnect(self, name: str) -> None:
        """Disconnect a specific MCP server."""
        conn = self.connections.pop(name, None)
        if not conn:
            return
        for tool in conn.tools:
            self._tool_to_server.pop(tool["name"], None)
        exit_stack = self._exit_stacks.pop(name, None)
        if exit_stack:
            try:
                await exit_stack.aclose()
            except Exception as e:
                logger.warning(f"Error disconnecting MCP server '{name}': {e}")
        logger.info(f"MCP server '{name}' disconnected")

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for name in list(self.connections.keys()):
            await self.disconnect(name)

    # ── Tool operations ────────────────────────────────────────────────

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all tools from all connected MCP servers."""
        await self._ensure_system_servers()
        tools = []
        for conn in self.connections.values():
            tools.extend(conn.tools)
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Call a tool by its unified name (server__tool_name)."""
        await self._ensure_system_servers()
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            raise ValueError(f"Tool '{tool_name}' not found in any connected MCP server")

        conn = self.connections[server_name]
        original_name = self._original_tool_name(tool_name, conn)

        logger.debug(f"Calling MCP tool '{original_name}' on server '{server_name}'")
        result = await conn.session.call_tool(original_name, arguments)
        return result

    def _tool_name(self, server_name: str, tool_name: str) -> str:
        """Create a unified tool name: server__tool_name."""
        return f"{server_name}__{tool_name}"

    def _original_tool_name(self, unified_name: str, conn: ServerConnection) -> str:
        """Extract original tool name from unified name for a given server."""
        prefix = f"{conn.name}__"
        if unified_name.startswith(prefix):
            return unified_name[len(prefix):]
        return unified_name

    # ── System servers ─────────────────────────────────────────────────

    async def start_system_servers(self) -> None:
        """Start the built-in system MCP servers (filesystem, shell, cloud_api).

        Idempotent: safe to call multiple times. Uses a flag to prevent duplicate spawns.
        """
        if getattr(self, "_system_servers_started", False):
            logger.debug("System MCP servers already started; skipping")
            return
        self._system_servers_started = True

        servers = [
            ("filesystem", sys.executable, ["-m", "app.mcp.servers.filesystem"]),
            ("shell", sys.executable, ["-m", "app.mcp.servers.shell"]),
            ("cloud_api", sys.executable, ["-m", "app.mcp.servers.cloud_api"]),
            ("desktop", sys.executable, ["-m", "app.mcp.servers.desktop"]),
        ]

        for name, command, args in servers:
            try:
                await self.connect_stdio(name, command, args)
            except asyncio.CancelledError:
                logger.warning(f"MCP server '{name}' connection was cancelled")
            except Exception as e:
                logger.error(f"Failed to start system MCP server '{name}': {e}")

    async def _ensure_system_servers(self) -> None:
        """Lazy on-demand startup for system servers."""
        if self is not mcp_client_manager:
            # Don't side-effect test instances
            return
        await self.start_system_servers()


# Global singleton
mcp_client_manager = MCPClientManager()
