"""Integration test for MCP tool parameter passing."""
import pytest
from unittest.mock import AsyncMock, patch

from app.tools.registry import MCPWrappedTool, ToolInput


@pytest.mark.asyncio
async def test_mcp_wrapped_tool_passes_parameters_correctly():
    """MCPWrappedTool should pass parameters dict to mcp_client_manager.call_tool."""
    tool = MCPWrappedTool(
        name="filesystem__write_file",
        description="Write a file",
        schema={"properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
    )

    mock_result = AsyncMock()
    mock_result.content = [AsyncMock(text="File written: /tmp/test.txt")]

    with patch("app.mcp.client_manager.mcp_client_manager") as mock_mcp:
        mock_mcp.call_tool = AsyncMock(return_value=mock_result)

        tool_input = ToolInput(parameters={"path": "/tmp/test.txt", "content": "hello world"})
        result = await tool.execute(tool_input)

    assert result.success is True
    assert "File written" in result.result["output"]
    mock_mcp.call_tool.assert_called_once_with("filesystem__write_file", {"path": "/tmp/test.txt", "content": "hello world"})


@pytest.mark.asyncio
async def test_mcp_wrapped_tool_remaps_task_id():
    """MCPWrappedTool should remap _task_id -> task_id for environment MCP servers."""
    tool = MCPWrappedTool(
        name="browser_env__navigate",
        description="Navigate browser",
        schema={"properties": {"url": {"type": "string"}}},
    )

    mock_result = AsyncMock()
    mock_result.content = [AsyncMock(text='{"success": true}')]

    with patch("app.mcp.client_manager.mcp_client_manager") as mock_mcp:
        mock_mcp.call_tool = AsyncMock(return_value=mock_result)

        tool_input = ToolInput(parameters={"_task_id": "task-42", "url": "https://example.com"})
        result = await tool.execute(tool_input)

    assert result.success is True
    # _task_id should be stripped but remapped to task_id
    mock_mcp.call_tool.assert_called_once_with(
        "browser_env__navigate",
        {"url": "https://example.com", "task_id": "task-42"},
    )
