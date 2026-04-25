from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ImplementationType(str, Enum):
    NATIVE = "native"
    MCP = "mcp"
    OPENAPI = "openapi"
    PYTHON = "python"
    DOCKER = "docker"


class ToolImplementation(BaseModel):
    type: ImplementationType
    config: Dict[str, Any] = Field(default_factory=dict)


class HealthMetrics(BaseModel):
    invocation_count: int = 0
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    last_check: Optional[str] = None


class ToolV2(BaseModel):
    tool_id: str
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None
    implementation: ToolImplementation
    category: str = "general"
    tags: List[str] = Field(default_factory=list)
    author: str = "system"
    dependencies: List[str] = Field(default_factory=list)
    sandboxed: bool = False
    timeout: int = 30
    max_retries: int = 2
    health: HealthMetrics = Field(default_factory=HealthMetrics)
