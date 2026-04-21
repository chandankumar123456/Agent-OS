from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from uuid import uuid4

Base = declarative_base()


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
    task_id = Column(String(36), nullable=False, index=True)
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
    span_id = Column(String(36), nullable=False, unique=True, index=True)
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
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConfigModel(Base):
    __tablename__ = "config"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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
