from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, Boolean, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
import uuid
from uuid import uuid4
from enum import Enum as PyEnum

class Base(DeclarativeBase):
    pass


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


class CheckpointWriteModel(Base):
    __tablename__ = "checkpoint_writes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    thread_id = Column(String(100), nullable=False, index=True)
    checkpoint_ns = Column(String(100), nullable=False, index=True)
    checkpoint_id = Column(String(100), nullable=False, index=True)
    task_id = Column(String(100), nullable=False, index=True)
    task_path = Column(String(255), nullable=True)
    write_data = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "task_path", name="uq_checkpoint_write"),
    )


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


# ============================================================================
# SECTION 5: DATA & STATE DESIGN - Extended Models
# ============================================================================

class CheckpointMetadataModel(Base):
    """Checkpoint metadata for chain traversal and replay.
    
    Extends the base CheckpointModel with rich metadata about
    which node, step, and decision context was active.
    """
    __tablename__ = "checkpoint_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    checkpoint_id = Column(String(100), nullable=False, index=True)
    thread_id = Column(String(100), nullable=False, index=True)
    task_id = Column(String(36), nullable=False, index=True)
    
    # Node and step information
    node_name = Column(String(100), nullable=False)  # planner_node, executor_node, etc.
    step_index = Column(Integer, nullable=True)  # Current step in plan
    step_type = Column(String(50), nullable=True)  # Type of step being executed
    
    # Decision context
    decision_context = Column(JSON, nullable=True)  # Why this checkpoint was saved
    decision_reason = Column(Text, nullable=True)  # Human-readable reason
    
    # Chain navigation
    parent_checkpoint_id = Column(String(100), nullable=True, index=True)
    child_checkpoint_ids = Column(JSON, default=list)  # List of child checkpoint IDs
    
    # Execution context
    agent_id = Column(String(36), nullable=True)  # Which agent was active
    tool_calls = Column(JSON, default=list)  # Tool calls made at this point
    recovery_attempts = Column(Integer, default=0)  # Number of recovery attempts
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("checkpoint_id", "thread_id", name="uq_checkpoint_metadata"),
    )


class UserMemoryProfileModel(Base):
    """User-level memory profile for cross-task knowledge retrieval.
    
    Stores learned patterns, preferences, and historical context
    that persists across multiple tasks for a user.
    """
    __tablename__ = "user_memory_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, unique=True, index=True)
    
    # Profile content
    learned_patterns = Column(JSON, default=list)  # List of learned patterns
    preferences = Column(JSON, default=dict)  # User preferences
    common_tasks = Column(JSON, default=list)  # Frequently executed task types
    recent_context = Column(JSON, default=list)  # Recent task summaries
    
    # Cross-task knowledge
    knowledge_entries = Column(JSON, default=list)  # Key-value knowledge pairs
    error_patterns = Column(JSON, default=list)  # Known error patterns and solutions
    success_strategies = Column(JSON, default=list)  # What worked well
    
    # Pruning and management
    last_pruned_at = Column(DateTime, nullable=True)
    entry_count = Column(Integer, default=0)
    profile_size_bytes = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ArtifactModel(Base):
    """Artifact storage metadata.
    
    Tracks artifacts produced by agents during task execution.
    Actual content stored in filesystem/S3; this is the metadata.
    """
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    artifact_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Ownership
    task_id = Column(String(36), nullable=False, index=True)
    agent_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    
    # Artifact details
    artifact_type = Column(String(50), nullable=False)  # file, image, document, etc.
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    mime_type = Column(String(100), nullable=True)
    
    # Storage
    storage_backend = Column(String(50), default="filesystem")  # filesystem, s3, etc.
    uri = Column(String(500), nullable=False)  # Full path/URL to artifact
    size_bytes = Column(Integer, nullable=True)
    checksum = Column(String(64), nullable=True)  # SHA-256 checksum
    
    # Metadata
    tags = Column(JSON, default=list)
    metadata_json = Column("metadata", JSON, nullable=True)  # Custom metadata
    
    # Lifecycle
    retention_days = Column(Integer, default=90)
    archived_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditModel(Base):
    """Complete audit trail for compliance.
    
    Immutable record of all significant actions in the system.
    """
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    audit_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=False, index=True)  # task_start, tool_call, approval, etc.
    event_action = Column(String(100), nullable=False)  # Specific action taken
    
    # Actors
    user_id = Column(String(36), nullable=True, index=True)  # Who triggered it
    task_id = Column(String(36), nullable=True, index=True)
    agent_id = Column(String(36), nullable=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    
    # Context
    resource_type = Column(String(50), nullable=True)  # task, tool, agent, etc.
    resource_id = Column(String(100), nullable=True)
    
    # Data (immutable record)
    request_data = Column(JSON, nullable=True)  # Input/request
    response_data = Column(JSON, nullable=True)  # Output/response
    
    # Outcome
    status = Column(String(20), nullable=False)  # success, failure, denied
    error_message = Column(Text, nullable=True)
    
    # Security
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(500), nullable=True)
    
    # Timestamp (separate from created_at for potential clock skew handling)
    event_timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Tamper-evident (optional - for high-security deployments)
    previous_audit_hash = Column(String(64), nullable=True)  # Chain of custody
    audit_hash = Column(String(64), nullable=True)  # Hash of this record


class AgentStateTransitionModel(Base):
    """Agent lifecycle state transitions.
    
    Tracks agents through their lifecycle: CREATED → REGISTERED → ACTIVE → EXECUTING → IDLE → DECOMMISSIONED
    """
    __tablename__ = "agent_state_transitions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id = Column(String(36), nullable=False, index=True)
    
    # State transition
    from_state = Column(String(50), nullable=False)
    to_state = Column(String(50), nullable=False)
    
    # Context
    triggered_by = Column(String(100), nullable=False)  # Component that triggered
    reason = Column(Text, nullable=True)  # Human-readable reason
    context = Column(JSON, nullable=True)  # Additional context
    
    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskQueueEntryModel(Base):
    """Task queue entries for priority-based scheduling.
    
    Tasks waiting to be executed with priority and scheduling info.
    """
    __tablename__ = "task_queue"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(36), nullable=False, unique=True, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    
    # Queue position
    priority = Column(String(20), default="normal")  # critical, high, normal, low
    priority_score = Column(Float, default=0.0)  # Computed priority score
    queue_position = Column(Integer, nullable=True)
    
    # Scheduling
    scheduled_at = Column(DateTime, nullable=True)  # When to execute (future scheduling)
    enqueue_time = Column(DateTime, default=datetime.utcnow)
    expected_start_time = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String(20), default="queued")  # queued, processing, completed, failed
    worker_id = Column(String(100), nullable=True)  # Assigned worker
    
    # Execution constraints
    required_capabilities = Column(JSON, default=list)
    excluded_workers = Column(JSON, default=list)
    
    # Timeouts
    timeout_seconds = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    # Metadata
    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
