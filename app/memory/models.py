from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, Boolean, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from datetime import datetime
import uuid
from uuid import uuid4
from enum import Enum as PyEnum

Base = declarative_base()


class ToolV2Model(Base):
    __tablename__ = "tools_v2"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    version = Column(String, default="1.0.0")
    input_schema = Column(JSON, default=dict)
    output_schema = Column(JSON, nullable=True)
    implementation_type = Column(String, nullable=False)
    implementation_config = Column(JSON, default=dict)
    category = Column(String, default="general", index=True)
    tags = Column(JSON, default=list)
    author = Column(String, default="system")
    dependencies = Column(JSON, default=list)
    sandboxed = Column(Boolean, default=False)
    timeout = Column(Integer, default=30)
    max_retries = Column(Integer, default=2)
    invocation_count = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0.0)
    error_rate = Column(Float, default=0.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GuardrailRuleType(str, PyEnum):
    blocked_keywords = "blocked_keywords"
    max_length = "max_length"
    required_fields = "required_fields"
    allowed_tools = "allowed_tools"


class GuardrailRuleAction(str, PyEnum):
    block = "block"
    warn = "warn"
    log = "log"


class GuardrailRuleStatus(str, PyEnum):
    active = "active"
    inactive = "inactive"


class TaskModel(Base):
    __tablename__ = "tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    query = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StepModel(Base):
    __tablename__ = "steps"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    agent_type = Column(String(20), nullable=False)
    status = Column(String(20), default="pending")
    depends_on = Column(JSON, nullable=True)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowModel(Base):
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True, unique=True)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    definition = Column(JSON, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowNodeModel(Base):
    __tablename__ = "workflow_nodes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id = Column(String(36), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    agent_type = Column(String(20), nullable=False)
    status = Column(String(20), default="pending")
    depends_on = Column(JSON, nullable=True)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    condition_code = Column(Text, nullable=True)
    node_type = Column(String(20), nullable=False, default="agent")
    approval_config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkflowEdgeModel(Base):
    __tablename__ = "workflow_edges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id = Column(String(36), nullable=False, index=True)
    from_node_id = Column(String(36), nullable=False, index=True)
    to_node_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContextModel(Base):
    __tablename__ = "context"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MessageModel(Base):
    __tablename__ = "messages"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    step_id = Column(String(36), nullable=True)
    sender = Column(String(50), nullable=False)
    receiver = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TraceModel(Base):
    __tablename__ = "traces"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    trace_id = Column(String(36), nullable=False, unique=True, index=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NodeTraceModel(Base):
    __tablename__ = "node_traces"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    trace_id = Column(String(36), nullable=False, index=True)
    node_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), default="pending")
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SpanModel(Base):
    __tablename__ = "spans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trace_id = Column(String(36), nullable=False, index=True)
    span_id = Column(String(255), nullable=False, unique=True, index=True)
    operation = Column(String(100), nullable=False)
    agent_name = Column(String(50), nullable=False)
    status = Column(String(20), default="pending")
    error = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)


class ToolModel(Base):
    __tablename__ = "tools"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default="custom")
    parameters_schema = Column(JSON, nullable=True)
    template = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MCPServerModel(Base):
    __tablename__ = "mcp_servers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), unique=True, nullable=False, index=True)
    endpoint = Column(String(500), nullable=False)
    tools_list = Column(JSON, nullable=True)
    auth_scope = Column(String(255), nullable=True)
    health_status = Column(String(20), default="unknown")
    version = Column(String(20), default="1.0.0")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentModel(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False)
    system_prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)
    tools = Column(JSON, nullable=True)
    version = Column(String(20), default="1.0.0")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentVersionModel(Base):
    __tablename__ = "agent_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_key = Column(String(100), nullable=False, index=True)
    version = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(50), nullable=False)
    system_prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)
    tools = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("agent_key", "version", name="uq_agent_version"),
    )


class ConfigModel(Base):
    __tablename__ = "config"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GuardrailRuleModel(Base):
    __tablename__ = "guardrail_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    rule_type = Column(String(30), nullable=False)
    condition = Column(JSON, nullable=False, default=dict)
    action = Column(String(20), nullable=False, default="block")
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    thread_id = Column(String(100), primary_key=True)
    checkpoint_ns = Column(String(100), primary_key=True, default="")
    checkpoint_id = Column(String(100), primary_key=True)
    parent_checkpoint_id = Column(String(100), nullable=True)
    checkpoint = Column(Text, nullable=False)
    checkpoint_metadata = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserModel(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    role = Column(String(20), nullable=False, default="user")
    hashed_password = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceModel(Base):
    __tablename__ = "workspaces"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(100), nullable=False)
    owner_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkspaceMemberModel(Base):
    __tablename__ = "workspace_members"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")
    joined_at = Column(DateTime, default=datetime.utcnow)


class APIKeyModel(Base):
    __tablename__ = "api_keys"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    workspace_id = Column(String(36), nullable=True, index=True)
    key_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    permissions = Column(JSON, default=list)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserOnboardingState(Base):
    __tablename__ = "user_onboarding_state"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, unique=True, nullable=False, index=True)
    has_completed_tour = Column(Boolean, default=False)
    has_created_first_task = Column(Boolean, default=False)
    has_created_first_agent = Column(Boolean, default=False)
    has_created_first_workflow = Column(Boolean, default=False)
    dismissed_prompts = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenUsageModel(Base):
    __tablename__ = "token_usage"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentConfigV2Model(Base):
    __tablename__ = "agent_config_v2"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    goal = Column(Text, default="")
    backstory = Column(Text, default="")
    model = Column(String, default="gpt-4o")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2048)
    reasoning = Column(Boolean, default=False)
    max_reasoning_attempts = Column(Integer, default=3)
    tools = Column(JSON, default=list)
    allow_delegation = Column(Boolean, default=False)
    memory_enabled = Column(Boolean, default=True)
    knowledge_sources = Column(JSON, default=list)
    max_iter = Column(Integer, default=20)
    max_execution_time = Column(Integer, default=300)
    max_retry_limit = Column(Integer, default=2)
    system_template = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=True)
    response_template = Column(Text, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    agent_id = Column(String(36), nullable=True, index=True)
    title = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeSourceModel(Base):
    __tablename__ = "knowledge_sources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String, nullable=False)
    type = Column(String(20), nullable=False)
    content_preview = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class KnowledgeChunkModel(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id = Column(String(36), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeploymentModel(Base):
    __tablename__ = "deployments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    workflow_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    endpoint_path = Column(String(200), unique=True, nullable=False, index=True)
    api_key_hash = Column(String(255), nullable=True)
    auth_type = Column(String(20), nullable=False, default="none")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
