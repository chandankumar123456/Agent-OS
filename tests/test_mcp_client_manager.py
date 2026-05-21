"""Tests for MCP client manager."""
import pytest
from unittest.mock import MagicMock

from core.mcp.client_manager import MCPClientManager


@pytest.mark.asyncio
async def test_client_manager_starts_empty():
    manager = MCPClientManager()
    tools = await manager.list_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_client_manager_tracks_connections():
    manager = MCPClientManager()
    assert manager.connections == {}
    assert manager._tool_to_server == {}


@pytest.mark.asyncio
async def test_disconnect_all_with_no_connections():
    manager = MCPClientManager()
    await manager.disconnect_all()
    assert manager.connections == {}


def test_tool_name_formatting():
    manager = MCPClientManager()
    name = manager._tool_name("filesystem", "read_file")
    assert name == "filesystem__read_file"


def test_original_tool_name_extraction():
    manager = MCPClientManager()
    conn = MagicMock()
    conn.name = "filesystem"
    original = manager._original_tool_name("filesystem__read_file", conn)
    assert original == "read_file"


def test_original_tool_name_no_prefix():
    manager = MCPClientManager()
    conn = MagicMock()
    conn.name = "filesystem"
    original = manager._original_tool_name("read_file", conn)
    assert original == "read_file"
