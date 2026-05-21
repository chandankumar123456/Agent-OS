"""MCP Code Execution Server — provides sandboxed Python code execution."""
# Stdout sanitization MUST be the first import to prevent any library from
# corrupting the JSON-RPC stdio transport.
import core.mcp.servers._stdio_sanitize  # noqa: F401, E402

import json
import os

os.environ["AGENTOS_LOG_STDERR"] = "1"

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("code_executor")

from core.tools.sandbox import ToolSandbox


@mcp.tool()
async def run_python(code: str, timeout: int = 30) -> str:
    """Execute Python code in a restricted sandbox and return the result.

    Args:
        code: Python code to execute. Assign the final result to a variable named 'result'.
        timeout: Maximum execution time in seconds (default 30).
    """
    if not code:
        return json.dumps({"success": False, "error": "No code provided"})

    try:
        sandbox = ToolSandbox(timeout=timeout)
        output = await sandbox.run("code_executor__run_python", code, {})
        if output.success:
            return json.dumps({"success": True, "result": output.result})
        return json.dumps({"success": False, "error": output.error})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
