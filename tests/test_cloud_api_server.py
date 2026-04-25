"""Tests for the cloud_api MCP server."""


def test_cloud_api_module_imports():
    from app.mcp.servers import cloud_api
    assert cloud_api.mcp.name == "cloud_api"
