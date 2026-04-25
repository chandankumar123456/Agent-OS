"""MCP Desktop Server — provides desktop automation tools to agents."""
import json
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("desktop")

from app.environments.desktop_env import desktop_session_manager


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
