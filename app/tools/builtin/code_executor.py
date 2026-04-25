from ..base import BaseTool, ToolInput, ToolOutput


class CodeExecutorRunPythonTool(BaseTool):
    name = "code_executor__run_python"
    description = "Execute Python code in a sandboxed environment using the ToolSandbox."
    parameters_schema = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute. Assign result to a variable named 'result'."},
        },
        "required": ["code"],
    }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = dict(tool_input.parameters)
        code = params.get("code", "")
        if not code:
            return ToolOutput(success=False, error="No code provided")

        try:
            from ..sandbox import ToolSandbox
            sandbox = ToolSandbox(timeout=30)
            return await sandbox.run(self.name, code, {})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))
