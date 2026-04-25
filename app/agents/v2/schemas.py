from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AgentToolBinding(BaseModel):
    tool_name: str
    param_bindings: Dict[str, str] = Field(default_factory=dict)
    required: bool = False
    fallback_tool: Optional[str] = None

class AgentConfigV2(BaseModel):
    agent_id: str
    name: str
    role: str
    goal: str = ""
    backstory: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2048
    reasoning: bool = False
    max_reasoning_attempts: int = 3
    tools: List[AgentToolBinding] = Field(default_factory=list)
    allow_delegation: bool = False
    memory_enabled: bool = True
    knowledge_sources: List[str] = Field(default_factory=list)
    max_iter: int = 20
    max_execution_time: int = 300
    max_retry_limit: int = 2
    system_template: Optional[str] = None
    prompt_template: Optional[str] = None
    response_template: Optional[str] = None
