import asyncio
from typing import Dict, Any
from ..logs.logger import logger
from .base import ToolOutput


# Allowed builtins for sandboxed execution
ALLOWED_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "ascii": ascii,
    "bin": bin,
    "bool": bool,
    "bytearray": bytearray,
    "bytes": bytes,
    "callable": callable,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hasattr": hasattr,
    "hash": hash,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
}

# Dangerous builtins that must be blocked
BLOCKED_NAMES = {"__import__", "open", "eval", "exec", "compile", "input", "print"}


class ToolSandbox:
    """Sandbox for executing custom tools with restricted Python environment."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _validate_code(self, code: str) -> None:
        """Validate that code does not contain dangerous constructs."""
        import ast
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Invalid tool code syntax: {e}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                raise SecurityError("Import statements are not allowed in tool code")
            if isinstance(node, ast.ImportFrom):
                raise SecurityError("Import statements are not allowed in tool code")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_NAMES:
                    raise SecurityError(f"Call to '{node.func.id}' is not allowed in tool code")
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in BLOCKED_NAMES:
                        raise SecurityError(f"Call to '{node.func.attr}' is not allowed in tool code")

    async def run(self, tool_name: str, code: str, parameters: Dict[str, Any]) -> ToolOutput:
        """Execute tool code in a sandboxed environment with timeout."""
        try:
            self._validate_code(code)
        except SecurityError as e:
            return ToolOutput(success=False, error=f"Security violation: {e}")
        except ValueError as e:
            return ToolOutput(success=False, error=str(e))

        # Run in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._execute_sync, tool_name, code, parameters),
                timeout=self.timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.error(f"Tool {tool_name} timed out after {self.timeout}s")
            return ToolOutput(success=False, error=f"Tool {tool_name} timed out after {self.timeout}s")
        except Exception as e:
            logger.error(f"Sandbox execution error for {tool_name}: {e}")
            return ToolOutput(success=False, error=str(e))

    def _execute_sync(self, tool_name: str, code: str, parameters: Dict[str, Any]) -> ToolOutput:
        """Synchronous execution in restricted environment."""
        # Prepare globals with restricted builtins
        restricted_globals = {"__builtins__": ALLOWED_BUILTINS.copy()}
        restricted_locals = {"params": parameters, "result": None}

        # Wrap user code in a function to capture result
        wrapped_code = f"""
{code}
"""
        try:
            exec(wrapped_code, restricted_globals, restricted_locals)
            result = restricted_locals.get("result")
            return ToolOutput(success=True, result=result)
        except Exception as e:
            logger.error(f"Tool {tool_name} execution failed: {e}")
            return ToolOutput(success=False, error=str(e))


class SecurityError(Exception):
    """Raised when tool code violates security policy."""
    pass
