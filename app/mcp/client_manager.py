"""MCP Client Manager — manages connections to MCP servers and routes tool calls."""
import asyncio
import os
import sys
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import AsyncExitStack

# Use explicit import to avoid conflict with local app.mcp package
import mcp as mcp_package
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

# Re-export for backward compatibility
ClientSession = mcp_package.ClientSession
StdioServerParameters = mcp_package.StdioServerParameters

from ..logs.logger import logger

# ExceptionGroup is standard in Python 3.11+
try:
    from builtins import BaseExceptionGroup, ExceptionGroup
except (ImportError, AttributeError):
    try:
        from exceptiongroup import BaseExceptionGroup, ExceptionGroup
    except ImportError:
        # Fallback: define minimal stubs so except clauses don't crash.
        # Use Exception (not BaseException) to avoid catching KeyboardInterrupt/SystemExit.
        BaseExceptionGroup = Exception
        ExceptionGroup = Exception


@dataclass
class CircuitBreakerState:
    failures: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"  # closed, open, half-open


class CircuitBreaker:
    """Circuit breaker pattern for MCP server connections.

    Tracks failures and prevents reconnection storms by temporarily
    blocking connection attempts after consecutive failures.
    """

    def __init__(self, threshold=3, recovery_timeout=30.0):
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self._states: Dict[str, CircuitBreakerState] = {}

    def record_failure(self, name: str):
        if name not in self._states:
            self._states[name] = CircuitBreakerState()
        state = self._states[name]
        state.failures += 1
        state.last_failure_time = time.time()
        if state.failures >= self.threshold:
            state.state = "open"

    def record_success(self, name: str):
        if name in self._states:
            self._states[name] = CircuitBreakerState()  # reset

    def can_proceed(self, name: str) -> bool:
        if name not in self._states:
            return True
        state = self._states[name]
        if state.state == "closed":
            return True
        if state.state == "open":
            if time.time() - state.last_failure_time >= self.recovery_timeout:
                state.state = "half-open"
                return True
            return False
        if state.state == "half-open":
            return True
        return True


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
        self._raw_contexts: Dict[str, Any] = {}
        self._circuit_breaker = CircuitBreaker()

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

        # Circuit breaker: prevent reconnection storms
        if not self._circuit_breaker.can_proceed(name):
            raise RuntimeError(
                f"MCP server '{name}' connection blocked by circuit breaker "
                f"(too many consecutive failures)"
            )

        logger.info(f"Connecting to MCP server '{name}' via stdio: {command} {args}")
        # Pass the full parent environment so MCP servers inherit OPENAI_API_KEY,
        # proxy settings, and other runtime configuration.  The mcp library's
        # default get_default_environment() strips most variables.
        merged_env = {**os.environ, **(env or {})}
        params = StdioServerParameters(
            command=command,
            args=args or [],
            env=merged_env,
        )

        exit_stack = AsyncExitStack()
        ctx = None
        try:
            # Enter stdio_client context
            ctx = stdio_client(params)
            read_stream, write_stream = await exit_stack.enter_async_context(ctx)
            self._raw_contexts[name] = ctx
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
            self._circuit_breaker.record_success(name)
            return conn
        except asyncio.TimeoutError:
            self._circuit_breaker.record_failure(name)
            if ctx:
                await self._safe_aclose_generator(name, ctx)
                self._raw_contexts.pop(name, None)
            await self._safe_close_exit_stack(name, exit_stack)
            raise RuntimeError(f"MCP server '{name}' initialization timed out")
        except Exception:
            self._circuit_breaker.record_failure(name)
            if ctx:
                await self._safe_aclose_generator(name, ctx)
                self._raw_contexts.pop(name, None)
            await self._safe_close_exit_stack(name, exit_stack)
            raise

    async def _safe_close_exit_stack(self, name: str, exit_stack: AsyncExitStack) -> None:
        """Gracefully close an AsyncExitStack, suppressing cross-task cleanup errors."""
        try:
            await exit_stack.aclose()
        except RuntimeError as e:
            logger.warning(
                f"RuntimeError during MCP server '{name}' disconnect (cross-task cleanup): {e}"
            )
        except GeneratorExit as e:
            logger.warning(
                f"GeneratorExit during MCP server '{name}' disconnect: {e}"
            )
        except BaseExceptionGroup as e:
            logger.warning(
                f"ExceptionGroup during MCP server '{name}' disconnect: {e}"
            )
        except Exception as e:
            logger.warning(f"Error disconnecting MCP server '{name}': {e}")

    async def _safe_aclose_generator(self, name: str, ctx) -> None:
        """Manually aclose the raw async generator to avoid finalizer stack traces."""
        gen = getattr(ctx, "gen", None)
        if gen is None:
            return
        try:
            await gen.aclose()
        except RuntimeError as e:
            logger.warning(
                f"RuntimeError during MCP server '{name}' generator cleanup (cross-task): {e}"
            )
        except GeneratorExit as e:
            logger.warning(
                f"GeneratorExit during MCP server '{name}' generator cleanup: {e}"
            )
        except BaseExceptionGroup as e:
            logger.warning(
                f"ExceptionGroup during MCP server '{name}' generator cleanup: {e}"
            )
        except Exception as e:
            logger.warning(f"Error during MCP server '{name}' generator cleanup: {e}")

    async def connect_http(self, name: str, url: str) -> ServerConnection:
        """Connect to an MCP server via HTTP/SSE transport.

        HTTP transport is not supported in AgentOS V1.
        Only stdio transport is available for MCP servers.
        """
        raise NotImplementedError(
            "MCP HTTP transport is not supported in AgentOS V1. "
            "Use connect_stdio() instead."
        )

    async def disconnect(self, name: str) -> None:
        """Disconnect a specific MCP server."""
        conn = self.connections.pop(name, None)
        if not conn:
            return
        for tool in conn.tools:
            self._tool_to_server.pop(tool["name"], None)
        # Manually close the raw stdio_client generator first to prevent
        # cross-task RuntimeError stack traces from the asyncgen finalizer.
        ctx = self._raw_contexts.pop(name, None)
        if ctx:
            await self._safe_aclose_generator(name, ctx)
        exit_stack = self._exit_stacks.pop(name, None)
        if exit_stack:
            await self._safe_close_exit_stack(name, exit_stack)
        logger.info(f"MCP server '{name}' disconnected")

    async def disconnect_all(self) -> None:
        """Disconnect all MCP servers."""
        for name in list(self.connections.keys()):
            try:
                await self.disconnect(name)
            except Exception as e:
                logger.warning(f"Error during disconnect_all for '{name}': {e}")

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
        """Start the built-in system MCP servers (filesystem, shell, cloud_api, etc.).

        Idempotent: safe to call multiple times. Uses a flag to prevent duplicate spawns.
        Uses ``asyncio.gather()`` to start all servers in parallel.
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
            ("browser_env", sys.executable, ["-m", "app.mcp.servers.browser"]),
            ("document", sys.executable, ["-m", "app.mcp.servers.document"]),
            ("code_executor", sys.executable, ["-m", "app.mcp.servers.code"]),
        ]

        async def _start_one(name: str, command: str, args: list) -> None:
            try:
                await self.connect_stdio(name, command, args)
            except asyncio.CancelledError:
                logger.warning(f"MCP server '{name}' connection was cancelled")
            except Exception as e:
                logger.error(f"Failed to start system MCP server '{name}': {e}")

        tasks = [_start_one(name, cmd, args) for name, cmd, args in servers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _ensure_system_servers(self) -> None:
        """Lazy on-demand startup for system servers."""
        if self is not mcp_client_manager:
            # Don't side-effect test instances
            return
        await self.start_system_servers()


# Global singleton
mcp_client_manager = MCPClientManager()
