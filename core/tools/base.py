from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod


class ToolInput(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolOutput(BaseModel):
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    visibility: Optional[Dict[str, Any]] = None


class BaseTool(ABC):
    name: str
    description: str
    parameters_schema: Optional[Dict[str, Any]] = None

    @abstractmethod
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        pass

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema or {}
        }
