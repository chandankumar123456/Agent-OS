import httpx
from typing import Dict, Any
from .base import BaseTool, ToolInput, ToolOutput
from ..logs.logger import logger


class SearchTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web for information"
    
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        query = tool_input.parameters.get("query", "")
        
        if not query:
            return ToolOutput(
                success=False,
                error="No query provided"
            )
        
        logger.info(f"SearchTool executing: {query}")
        
        return ToolOutput(
            success=True,
            result={"query": query, "results": []},
            metadata={"provider": "mock"}
        )


class CalculatorTool(BaseTool):
    name: str = "calculator"
    description: str = "Perform calculations"
    
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        operation = tool_input.parameters.get("operation", "")
        a = tool_input.parameters.get("a", 0)
        b = tool_input.parameters.get("b", 0)
        result = 0
        
        try:
            if operation == "add":
                result = a + b
            elif operation == "subtract":
                result = a - b
            elif operation == "multiply":
                result = a * b
            elif operation == "divide":
                if b != 0:
                    result = a / b
                else:
                    return ToolOutput(success=False, error="Division by zero")
            else:
                return ToolOutput(success=False, error=f"Unknown operation: {operation}")
            
            return ToolOutput(
                success=True,
                result={"operation": operation, "a": a, "b": b, "result": result}
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))


class TextProcessorTool(BaseTool):
    name: str = "text_processor"
    description: str = "Process and transform text"
    
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        text = tool_input.parameters.get("text", "")
        operation = tool_input.parameters.get("operation", "uppercase")
        
        try:
            if operation == "uppercase":
                result = text.upper()
            elif operation == "lowercase":
                result = text.lower()
            elif operation == "length":
                result = len(text)
            else:
                return ToolOutput(success=False, error=f"Unknown operation: {operation}")
            
            return ToolOutput(
                success=True,
                result={"original": text, "processed": result, "operation": operation}
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))