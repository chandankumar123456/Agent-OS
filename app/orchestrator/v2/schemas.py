from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class NodeType(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    DECISION = "decision"
    WAIT = "wait"
    SUBFLOW = "subflow"
    MAP = "map"

class TriggerType(str, Enum):
    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"
    EVENT = "event"

class WorkflowNodeV2(BaseModel):
    node_id: str
    name: str
    type: NodeType
    config: Dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[str] = None
    tool_bindings: List[Dict[str, Any]] = Field(default_factory=list)
    map_over: Optional[str] = None
    condition: Optional[str] = None
    timeout: int = 300
    retry_count: int = 2

class WorkflowEdgeV2(BaseModel):
    from_node: str
    to_node: str
    condition: Optional[str] = None
    label: Optional[str] = None

class Trigger(BaseModel):
    type: TriggerType
    config: Dict[str, Any] = Field(default_factory=dict)

class WorkflowDefinitionV2(BaseModel):
    workflow_id: str
    name: str
    version: str = "1.0.0"
    triggers: List[Trigger] = Field(default_factory=list)
    nodes: List[WorkflowNodeV2]
    edges: List[WorkflowEdgeV2]
    max_retries: int = 3
    retry_delay: int = 5
