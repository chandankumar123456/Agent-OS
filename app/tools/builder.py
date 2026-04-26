"""Dynamic Tool Builder — builds missing tools on-the-fly."""
import asyncio
from typing import Dict, Any, Optional, Callable
from ..tools.base import BaseTool, ToolInput, ToolOutput
from ..logs.logger import logger


class DynamicToolFactory:
    """Creates tools dynamically when they are missing."""

    def __init__(self, registry):
        self.registry = registry
        self._built_tools: set = set()

    async def ensure_tool(self, tool_name: str) -> bool:
        """Check if tool exists; if not, try to build it. Returns True if available."""
        if self.registry.get(tool_name):
            return True
        if tool_name in self._built_tools:
            return self.registry.get(tool_name) is not None

        logger.info(f"[DynamicToolFactory] Tool '{tool_name}' missing. Attempting to build...")
        built = await self._build_tool(tool_name)
        if built:
            self._built_tools.add(tool_name)
        return built

    async def _build_tool(self, tool_name: str) -> bool:
        """Attempt to construct a missing tool."""
        if tool_name.startswith("filesystem__"):
            return await self._build_filesystem_tool(tool_name)
        if tool_name.startswith("document__"):
            return await self._build_document_tool(tool_name)
        if tool_name.startswith("shell__"):
            return await self._build_shell_tool(tool_name)
        return False

    async def _build_filesystem_tool(self, tool_name: str) -> bool:
        if tool_name == "filesystem__search_files":
            return self._register_from_callable(
                tool_name,
                self._search_files_impl,
                "Search for files matching a pattern.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "pattern": {"type": "string"},
                    },
                    "required": ["path", "pattern"],
                },
            )
        if tool_name == "filesystem__list_directory":
            return self._register_from_callable(
                tool_name,
                self._list_directory_impl,
                "List directory contents.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
        if tool_name == "filesystem__read_file":
            return self._register_from_callable(
                tool_name,
                self._read_file_impl,
                "Read file contents.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            )
        if tool_name == "filesystem__write_file":
            return self._register_from_callable(
                tool_name,
                self._write_file_impl,
                "Write content to a file.",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            )
        return False

    def _register_from_callable(
        self, name: str, fn: Callable, description: str, schema: Dict[str, Any]
    ) -> bool:
        """Wrap a Python function as a BaseTool and register it."""
        def _make_tool_class(tool_name: str, tool_description: str, tool_schema: Dict[str, Any], tool_fn: Callable):
            class DynamicTool(BaseTool):
                _tool_name = tool_name
                _tool_description = tool_description
                _tool_schema = tool_schema
                _tool_fn = tool_fn

                @property
                def name(self):
                    return self._tool_name

                @property
                def description(self):
                    return self._tool_description

                def get_schema(self):
                    return {
                        "name": self._tool_name,
                        "description": self._tool_description,
                        "parameters": self._tool_schema,
                    }

                async def execute(self, tool_input: ToolInput) -> ToolOutput:
                    try:
                        if asyncio.iscoroutinefunction(self._tool_fn):
                            result = await self._tool_fn(**tool_input.parameters)
                        else:
                            result = self._tool_fn(**tool_input.parameters)
                        if isinstance(result, ToolOutput):
                            return result
                        return ToolOutput(success=True, result={"output": result})
                    except Exception as e:
                        return ToolOutput(success=False, error=str(e))

            return DynamicTool

        ToolClass = _make_tool_class(name, description, schema, fn)
        self.registry.register(ToolClass())
        logger.info(f"[DynamicToolFactory] Registered dynamic tool: {name}")
        return True

    @staticmethod
    async def _search_files_impl(path: str, pattern: str) -> ToolOutput:
        from ..tools.file_discovery import FastFileDiscovery
        engine = FastFileDiscovery()
        matches = await engine.search(path, pattern, max_results=100)
        return ToolOutput(success=True, result={"matches": matches, "count": len(matches)})

    @staticmethod
    def _list_directory_impl(path: str) -> ToolOutput:
        import os
        if not os.path.isdir(path):
            return ToolOutput(success=False, error=f"Not a directory: {path}")
        entries = os.listdir(path)
        files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        return ToolOutput(success=True, result={"path": path, "files": files, "directories": dirs})

    @staticmethod
    def _read_file_impl(path: str) -> ToolOutput:
        import os
        if not os.path.exists(path):
            return ToolOutput(success=False, error=f"File not found: {path}")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return ToolOutput(success=True, result={"path": path, "content": content, "size": len(content)})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    @staticmethod
    def _write_file_impl(path: str, content: str) -> ToolOutput:
        import os
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolOutput(success=True, result={"path": path, "bytes_written": len(content.encode("utf-8"))})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def _build_document_tool(self, tool_name: str) -> bool:
        if tool_name in ("document__parse", "document__parse_pdf", "document__parse_docx", "document__parse_txt", "document__parse_markdown"):
            from ..pipelines.document_ingestion import DocumentParseTool
            self.registry.register(DocumentParseTool())
            return True
        return False

    async def _build_shell_tool(self, tool_name: str) -> bool:
        if tool_name == "shell__execute_command":
            return self._register_from_callable(
                tool_name,
                self._shell_execute_impl,
                "Execute a shell command and return output.",
                {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer", "default": 60},
                    },
                    "required": ["command"],
                },
            )
        return False

    @staticmethod
    async def _shell_execute_impl(command: str, timeout: int = 60) -> ToolOutput:
        import asyncio
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ToolOutput(
                success=proc.returncode == 0,
                result={
                    "stdout": stdout.decode("utf-8", errors="ignore"),
                    "stderr": stderr.decode("utf-8", errors="ignore"),
                    "returncode": proc.returncode,
                },
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolOutput(success=False, error=f"Command timed out after {timeout}s")


# Singleton instantiated after registry
dynamic_tool_factory: Optional[DynamicToolFactory] = None


def init_dynamic_tool_factory(registry):
    global dynamic_tool_factory
    dynamic_tool_factory = DynamicToolFactory(registry)
