"""MCP Desktop Server — provides desktop automation tools to agents."""
# Stdout sanitization MUST be the first import to prevent any library from
# corrupting the JSON-RPC stdio transport.
import core.mcp.servers._stdio_sanitize  # noqa: F401, E402

import os
import sys

os.environ["AGENTOS_LOG_STDERR"] = "1"

import json
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("desktop")

from core.environments.desktop_env import desktop_session_manager


async def _get_session(task_id: str = "default"):
    return await desktop_session_manager.get_or_create_session(task_id)


def _fmt(tool_output) -> str:
    if tool_output.success:
        return json.dumps({"success": True, "result": tool_output.result})
    return json.dumps({"success": False, "error": tool_output.error})


@mcp.tool()
async def desktop__screenshot(task_id: str = "default", path: Optional[str] = None) -> str:
    """Capture a screenshot of the primary monitor.

    Args:
        task_id: Task-scoped session identifier.
        path: Destination file path (optional).
    """
    session = await _get_session(task_id)
    result = await session.screenshot(path=path)
    return _fmt(result)


@mcp.tool()
async def desktop__click(task_id: str = "default", x: int = 0, y: int = 0) -> str:
    """Click at screen coordinates (x, y).

    Args:
        task_id: Task-scoped session identifier.
        x: Horizontal pixel coordinate.
        y: Vertical pixel coordinate.
    """
    session = await _get_session(task_id)
    result = await session.click(x, y)
    return _fmt(result)


@mcp.tool()
async def desktop__type_text(
    task_id: str = "default", text: str = "", interval: float = 0.01
) -> str:
    """Type text as keyboard input.

    Args:
        task_id: Task-scoped session identifier.
        text: Text to type.
        interval: Seconds between keystrokes.
    """
    session = await _get_session(task_id)
    result = await session.type_text(text, interval=interval)
    return _fmt(result)


@mcp.tool()
async def desktop__press_key(task_id: str = "default", keys: str = "") -> str:
    """Press a key or key combination (e.g., 'enter', 'ctrl+c', 'alt+f4').

    Args:
        task_id: Task-scoped session identifier.
        keys: Key or combination to press.
    """
    session = await _get_session(task_id)
    result = await session.press_key(keys)
    return _fmt(result)


@mcp.tool()
async def desktop__get_window_list(task_id: str = "default") -> str:
    """List visible windows.

    Args:
        task_id: Task-scoped session identifier.
    """
    session = await _get_session(task_id)
    result = await session.get_window_list()
    return _fmt(result)


@mcp.tool()
async def desktop__focus_window(task_id: str = "default", title: str = "") -> str:
    """Focus a window by title.

    Args:
        task_id: Task-scoped session identifier.
        title: Window title substring to match.
    """
    session = await _get_session(task_id)
    result = await session.focus_window(title)
    return _fmt(result)


@mcp.tool()
async def desktop__get_clipboard(task_id: str = "default") -> str:
    """Get the current clipboard text.

    Args:
        task_id: Task-scoped session identifier.
    """
    session = await _get_session(task_id)
    result = await session.get_clipboard()
    return _fmt(result)


@mcp.tool()
async def desktop__set_clipboard(task_id: str = "default", text: str = "") -> str:
    """Set the clipboard text.

    Args:
        task_id: Task-scoped session identifier.
        text: Text to place on the clipboard.
    """
    session = await _get_session(task_id)
    result = await session.set_clipboard(text)
    return _fmt(result)


@mcp.tool()
async def desktop__get_ui_tree(task_id: str = "default") -> str:
    """Dump the pruned accessibility tree.

    Args:
        task_id: Task-scoped session identifier.
    """
    session = await _get_session(task_id)
    result = await session.get_ui_tree()
    return _fmt(result)


@mcp.tool()
async def desktop__click_element(task_id: str = "default", element_id: int = 0) -> str:
    """Click a UI element by its element_id.

    Args:
        task_id: Task-scoped session identifier.
        element_id: ID of the UI element to click.
    """
    session = await _get_session(task_id)
    result = await session.click_element(element_id)
    return _fmt(result)


@mcp.tool()
async def desktop__type_element(
    task_id: str = "default", element_id: int = 0, text: str = ""
) -> str:
    """Focus an element and type text.

    Args:
        task_id: Task-scoped session identifier.
        element_id: ID of the UI element to focus.
        text: Text to type.
    """
    session = await _get_session(task_id)
    result = await session.type_element(element_id, text)
    return _fmt(result)


@mcp.tool()
async def desktop__focus_and_interact(
    task_id: str = "default", element_id: int = 0, key: str = "enter"
) -> str:
    """Force focus and simulate a key press.

    Args:
        task_id: Task-scoped session identifier.
        element_id: ID of the UI element to focus.
        key: Key to press (default is 'enter').
    """
    session = await _get_session(task_id)
    result = await session.focus_and_interact(element_id, key)
    return _fmt(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
