"""MCP Browser Server — provides browser automation tools via Playwright."""
# Stdout sanitization MUST be the first import to prevent any library from
# corrupting the JSON-RPC stdio transport.
import app.mcp.servers._stdio_sanitize  # noqa: F401, E402

import json
import os
import sys
from typing import Optional

# ALSO set the env var so our internal AgentOSLogger uses stderr.
os.environ["AGENTOS_LOG_STDERR"] = "1"

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("browser_env")

from app.environments.browser_env import browser_session_manager


def _fmt(tool_output) -> str:
    if tool_output.success:
        return json.dumps({"success": True, "result": tool_output.result})
    return json.dumps({"success": False, "error": tool_output.error})


@mcp.tool()
async def launch(task_id: str = "default", headless: bool = False) -> str:
    """Launch or bind to a browser session for the given task."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.launch(headless=headless)
    return _fmt(result)


@mcp.tool()
async def navigate(task_id: str = "default", url: str = "") -> str:
    """Navigate the browser to a URL."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.navigate(url)
    return _fmt(result)


@mcp.tool()
async def search(task_id: str = "default", query: str = "") -> str:
    """Search for a query on the current page."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.search(query)
    return _fmt(result)


@mcp.tool()
async def click(task_id: str = "default", selector: str = "") -> str:
    """Click an element matching a CSS selector."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.click(selector)
    return _fmt(result)


@mcp.tool()
async def type(task_id: str = "default", selector: str = "", text: str = "") -> str:
    """Type text into an element matching a CSS selector."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.type_text(selector, text)
    return _fmt(result)


@mcp.tool()
async def screenshot(task_id: str = "default", path: Optional[str] = None) -> str:
    """Capture a screenshot of the current page."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.screenshot(path)
    return _fmt(result)


@mcp.tool()
async def get_text(task_id: str = "default", selector: Optional[str] = None) -> str:
    """Extract text from the page or from a specific element."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.get_text(selector)
    return _fmt(result)


@mcp.tool()
async def close(task_id: str = "default") -> str:
    """Close the browser session for the given task."""
    result = await browser_session_manager.close_session(task_id)
    return _fmt(result)


@mcp.tool()
async def get_url(task_id: str = "default") -> str:
    """Get the current page URL."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.get_url()
    return _fmt(result)


@mcp.tool()
async def get_title(task_id: str = "default") -> str:
    """Get the current page title."""
    session = await browser_session_manager.get_or_create_session(task_id)
    result = await session.get_title()
    return _fmt(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
