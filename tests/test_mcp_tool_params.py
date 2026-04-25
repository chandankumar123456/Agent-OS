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
