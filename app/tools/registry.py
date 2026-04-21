from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from .base import BaseTool, ToolInput, ToolOutput
from .search import SearchTool, CalculatorTool, TextProcessorTool
from ..logs.logger import logger


@dataclass
class RegisteredTool:
    name: str
    description: str
    type: str
    tool: BaseTool


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, RegisteredTool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        self.register(SearchTool())
        self.register(CalculatorTool())
        self.register(TextProcessorTool())
        logger.info("Default tools registered")
    
    def register(self, tool: BaseTool):
        self.tools[tool.name] = RegisteredTool(
            name=tool.name,
            description=tool.description,
            type=getattr(tool, "tool_type", "builtin"),
            tool=tool,
        )
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        registered = self.tools.get(name)
        return registered.tool if registered else None

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                **registered.tool.get_schema(),
                "type": registered.type,
                "status": "active",
            }
            for registered in self.tools.values()
        ]
    
    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ToolOutput:
        tool = self.get(tool_name)
        
        if not tool:
            return ToolOutput(
                success=False,
                error=f"Tool not found: {tool_name}"
            )
        
        try:
            tool_input = ToolInput(parameters=parameters)
            result = await tool.execute(tool_input)
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return ToolOutput(success=False, error=str(e))


tool_registry = ToolRegistry()
