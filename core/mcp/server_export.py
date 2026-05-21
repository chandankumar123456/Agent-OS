from typing import Dict, Any

async def generate_mcp_server(workflow_id: str, user_id: str) -> Dict[str, Any]:
    """Generate an MCP server configuration that wraps a workflow as a tool."""
    return {
        "mcp_server": {
            "name": f"workflow_{workflow_id}",
            "version": "1.0.0",
            "transport": "stdio",
            "tools": [
                {
                    "name": "execute_workflow",
                    "description": f"Execute deployed workflow {workflow_id}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "object",
                                "description": "Input parameters for the workflow"
                            }
                        },
                        "required": ["input"]
                    }
                }
            ],
            "config": {
                "workflow_id": workflow_id,
                "user_id": user_id,
                "endpoint_url": f"/public/{workflow_id}",
            },
            "setup_instructions": [
                "1. Install the MCP server package",
                "2. Add this config to your MCP client settings",
                "3. The server will expose 'execute_workflow' as an available tool",
            ],
            "json_config": {
                "mcpServers": {
                    f"agentos_workflow_{workflow_id}": {
                        "command": "python",
                        "args": ["-m", "mcp.server.fastmcp", "--transport", "stdio"],
                        "env": {
                            "AGENTOS_WORKFLOW_ID": workflow_id,
                            "AGENTOS_API_URL": "http://localhost:8000"
                        }
                    }
                }
            }
        }
    }
