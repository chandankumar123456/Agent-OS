from typing import Dict, List, Optional, Any
from .base import BaseTool, ToolInput, ToolOutput
from .search import SearchTool, CalculatorTool, TextProcessorTool
from ..logs.logger import logger


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        self.register(SearchTool())
        self.register(CalculatorTool())
        self.register(TextProcessorTool())
        logger.info("Default tools registered")
    
    def register(self, tool: BaseTool):
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.get_schema() for tool in self.tools.values()]
    
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