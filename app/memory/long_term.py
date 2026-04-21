from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from datetime import datetime
from typing import Optional, Dict, Any, List
from types import SimpleNamespace
from uuid import uuid4

from .models import (
    Base,
    TaskModel,
    StepModel,
    WorkflowModel,
    WorkflowNodeModel,
    WorkflowEdgeModel,
    UserModel,
    TraceModel,
    NodeTraceModel,
    SpanModel,
    ToolModel,
    AgentModel,
    ConfigModel,
)
from ..config.settings import settings
from ..logs.logger import logger

DATABASE_URL = settings.DATABASE_URL or "postgresql+asyncpg://agentos:agentos@localhost:5432/agentos"

_MEMORY_TASKS: Dict[str, Any] = {}
_MEMORY_STEPS: Dict[str, Any] = {}
_MEMORY_USERS: Dict[str, Any] = {}
_MEMORY_TOOLS: Dict[str, Any] = {}
_MEMORY_AGENTS: Dict[str, Any] = {}
_MEMORY_CONFIG: Dict[str, Any] = {}
_MEMORY_TRACES: Dict[str, Any] = {}
_MEMORY_NODE_TRACES: Dict[str, Any] = {}
_MEMORY_SPANS: Dict[str, Any] = {}
_MEMORY_WORKFLOWS: Dict[str, Any] = {}
_MEMORY_WORKFLOW_NODES: Dict[str, Any] = {}
_MEMORY_WORKFLOW_EDGES: Dict[str, Any] = {}


def _memory_row(**kwargs):
    return SimpleNamespace(**kwargs)


def _fallback_log(scope: str, error: Exception) -> None:
    logger.warning(f"DB failure in {scope}, using in-memory fallback: {error}")


class Database:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def connect(self):
        try:
            self.engine = create_async_engine(DATABASE_URL, echo=False)
            self.session_factory = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database connected")
        except Exception as e:
            self.engine = None
            self.session_factory = None
            logger.warning(f"Database unavailable, using in-memory fallback: {e}")

    async def disconnect(self):
        if self.engine:
            await self.engine.dispose()
            logger.info("Database disconnected")

    def get_session(self) -> AsyncSession:
        if not self.session_factory:
            raise RuntimeError("Database session factory is unavailable")
        return self.session_factory()


db = Database()


class TaskRepository:
    async def create(self, task_id: str, query: str, user_id: str = "system", status: str = "pending") -> TaskModel:
        try:
            async with db.get_session() as session:
                task = TaskModel(id=task_id, query=query, user_id=user_id, status=status)
                session.add(task)
                await session.commit()
                await session.refresh(task)
                return task
        except Exception as e:
            _fallback_log("TaskRepository.create", e)
            task = _memory_row(
                id=task_id,
                query=query,
                user_id=user_id,
                status=status,
                result=None,
                error=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_TASKS[task_id] = task
            return task

    async def get(self, task_id: str) -> Optional[TaskModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("TaskRepository.get", e)
            return _MEMORY_TASKS.get(task_id)

    async def update(
        self,
        task_id: str,
        status: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskModel]:
        try:
            async with db.get_session() as session:
                result_obj = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
                task = result_obj.scalar_one_or_none()

                if task:
                    if status:
                        task.status = status
                    if result is not None:
                        task.result = result
                    if error:
                        task.error = error
                    await session.commit()
                    await session.refresh(task)

                return task
        except Exception as e:
            _fallback_log("TaskRepository.update", e)
            task = _MEMORY_TASKS.get(task_id)
            if task:
                if status:
                    task.status = status
                if result is not None:
                    task.result = result
                if error:
                    task.error = error
                task.updated_at = datetime.utcnow()
            return task

    async def list_all(self) -> List[TaskModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(TaskModel).order_by(TaskModel.created_at.desc()))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("TaskRepository.list_all", e)
            return sorted(_MEMORY_TASKS.values(), key=lambda task: task.created_at, reverse=True)


class StepRepository:
    async def create(
        self,
        step_id: str,
        task_id: str,
        step_number: int,
        agent_type: str,
        depends_on: Optional[List[int]] = None,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> StepModel:
        try:
            async with db.get_session() as session:
                step = StepModel(
                    id=step_id,
                    task_id=task_id,
                    step_number=step_number,
                    agent_type=agent_type,
                    depends_on=depends_on or [],
                    input_data=input_data,
                )
                session.add(step)
                await session.commit()
                await session.refresh(step)
                return step
        except Exception as e:
            _fallback_log("StepRepository.create", e)
            step = _memory_row(
                id=step_id,
                task_id=task_id,
                step_number=step_number,
                agent_type=agent_type,
                status="pending",
                depends_on=depends_on or [],
                input_data=input_data,
                output_data=None,
                confidence=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_STEPS[step_id] = step
            return step

    async def update(
        self,
        step_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> Optional[StepModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(StepModel).where(StepModel.id == step_id))
                step = result.scalar_one_or_none()

                if step:
                    if status:
                        step.status = status
                    if output_data is not None:
                        step.output_data = output_data
                    if confidence is not None:
                        step.confidence = confidence
                    await session.commit()
                    await session.refresh(step)

                return step
        except Exception as e:
            _fallback_log("StepRepository.update", e)
            step = _MEMORY_STEPS.get(step_id)
            if step:
                if status:
                    step.status = status
                if output_data is not None:
                    step.output_data = output_data
                if confidence is not None:
                    step.confidence = confidence
                step.updated_at = datetime.utcnow()
            return step

    async def get_by_task(self, task_id: str) -> List[StepModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(StepModel).where(StepModel.task_id == task_id).order_by(StepModel.step_number)
                )
                return result.scalars().all()
        except Exception as e:
            _fallback_log("StepRepository.get_by_task", e)
            return sorted([step for step in _MEMORY_STEPS.values() if step.task_id == task_id], key=lambda step: step.step_number)


class WorkflowRepository:
    async def create(
        self,
        task_id: str,
        user_id: str = "system",
        name: Optional[str] = None,
        definition: Optional[Dict[str, Any]] = None,
        status: str = "pending",
    ) -> WorkflowModel:
        try:
            async with db.get_session() as session:
                workflow = WorkflowModel(task_id=task_id, user_id=user_id, name=name, definition=definition or {}, status=status)
                session.add(workflow)
                await session.commit()
                await session.refresh(workflow)
                return workflow
        except Exception as e:
            _fallback_log("WorkflowRepository.create", e)
            workflow = _memory_row(
                id=str(uuid4()),
                task_id=task_id,
                user_id=user_id,
                name=name,
                definition=definition or {},
                status=status,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_WORKFLOWS[workflow.id] = workflow
            return workflow

    async def get_by_task(self, task_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(WorkflowModel).where(WorkflowModel.task_id == task_id))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("WorkflowRepository.get_by_task", e)
            return next((workflow for workflow in _MEMORY_WORKFLOWS.values() if workflow.task_id == task_id), None)


class WorkflowNodeRepository:
    async def create(
        self,
        workflow_id: str,
        step_number: int,
        agent_type: str,
        depends_on: Optional[List[str]] = None,
        input_data: Optional[Dict[str, Any]] = None,
        condition_code: Optional[str] = None,
    ) -> WorkflowNodeModel:
        try:
            async with db.get_session() as session:
                node = WorkflowNodeModel(
                    workflow_id=workflow_id,
                    step_number=step_number,
                    agent_type=agent_type,
                    depends_on=depends_on or [],
                    input_data=input_data,
                    condition_code=condition_code,
                )
                session.add(node)
                await session.commit()
                await session.refresh(node)
                return node
        except Exception as e:
            _fallback_log("WorkflowNodeRepository.create", e)
            node = _memory_row(
                id=str(uuid4()),
                workflow_id=workflow_id,
                step_number=step_number,
                agent_type=agent_type,
                status="pending",
                depends_on=depends_on or [],
                input_data=input_data,
                output_data=None,
                confidence=None,
                condition_code=condition_code,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_WORKFLOW_NODES[node.id] = node
            return node

    async def update(
        self,
        node_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(WorkflowNodeModel).where(WorkflowNodeModel.id == node_id))
                node = result.scalar_one_or_none()
                if node:
                    if status:
                        node.status = status
                    if output_data is not None:
                        node.output_data = output_data
                    if confidence is not None:
                        node.confidence = confidence
                    await session.commit()
                    await session.refresh(node)
                return node
        except Exception as e:
            _fallback_log("WorkflowNodeRepository.update", e)
            node = _MEMORY_WORKFLOW_NODES.get(node_id)
            if node:
                if status:
                    node.status = status
                if output_data is not None:
                    node.output_data = output_data
                if confidence is not None:
                    node.confidence = confidence
                node.updated_at = datetime.utcnow()
            return node

    async def get_by_workflow(self, workflow_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(WorkflowNodeModel).where(WorkflowNodeModel.workflow_id == workflow_id).order_by(WorkflowNodeModel.step_number)
                )
                return result.scalars().all()
        except Exception as e:
            _fallback_log("WorkflowNodeRepository.get_by_workflow", e)
            return sorted(
                [node for node in _MEMORY_WORKFLOW_NODES.values() if node.workflow_id == workflow_id],
                key=lambda node: node.step_number,
            )


class WorkflowEdgeRepository:
    async def create(self, workflow_id: str, from_node_id: str, to_node_id: str) -> WorkflowEdgeModel:
        try:
            async with db.get_session() as session:
                edge = WorkflowEdgeModel(workflow_id=workflow_id, from_node_id=from_node_id, to_node_id=to_node_id)
                session.add(edge)
                await session.commit()
                await session.refresh(edge)
                return edge
        except Exception as e:
            _fallback_log("WorkflowEdgeRepository.create", e)
            edge = _memory_row(
                id=str(uuid4()),
                workflow_id=workflow_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                created_at=datetime.utcnow(),
            )
            _MEMORY_WORKFLOW_EDGES[edge.id] = edge
            return edge

    async def get_by_workflow(self, workflow_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_id == workflow_id))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("WorkflowEdgeRepository.get_by_workflow", e)
            return [edge for edge in _MEMORY_WORKFLOW_EDGES.values() if edge.workflow_id == workflow_id]


workflow_repo = WorkflowRepository()
workflow_node_repo = WorkflowNodeRepository()
workflow_edge_repo = WorkflowEdgeRepository()


task_repo = TaskRepository()
class UserRepository:
    async def create(
        self,
        user_id: str,
        email: str,
        hashed_password: str,
        name: Optional[str] = None,
        api_key: Optional[str] = None,
        role: str = "user",
    ) -> UserModel:
        try:
            async with db.get_session() as session:
                user = UserModel(id=user_id, email=email, hashed_password=hashed_password, name=name, api_key=api_key, role=role)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
        except Exception as e:
            _fallback_log("UserRepository.create", e)
            user = _memory_row(
                id=user_id,
                email=email,
                hashed_password=hashed_password,
                name=name,
                api_key=api_key,
                role=role,
                is_active=True,
                created_at=datetime.utcnow(),
            )
            _MEMORY_USERS[user_id] = user
            return user

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(UserModel).where(UserModel.email == email))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("UserRepository.get_by_email", e)
            return next((user for user in _MEMORY_USERS.values() if user.email == email), None)

    async def get_by_id(self, user_id: str) -> Optional[UserModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(UserModel).where(UserModel.id == user_id))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("UserRepository.get_by_id", e)
            return _MEMORY_USERS.get(user_id)

    async def get_by_api_key(self, api_key: str) -> Optional[UserModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(UserModel).where(UserModel.api_key == api_key))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("UserRepository.get_by_api_key", e)
            return next((user for user in _MEMORY_USERS.values() if user.api_key == api_key), None)

    async def update_api_key(self, user_id: str, api_key: str) -> Optional[UserModel]:
        try:
            async with db.get_session() as session:
                result = await session.execute(select(UserModel).where(UserModel.id == user_id))
                user = result.scalar_one_or_none()

                if user:
                    user.api_key = api_key
                    await session.commit()
                    await session.refresh(user)

                return user
        except Exception as e:
            _fallback_log("UserRepository.update_api_key", e)
            user = _MEMORY_USERS.get(user_id)
            if user:
                user.api_key = api_key
            return user


user_repo = UserRepository()


class TraceRepository:
    async def create(self, task_id: str, trace_id: str, user_id: str, status: str = "pending"):
        try:
            async with db.get_session() as session:
                existing = await session.execute(select(TraceModel).where(TraceModel.trace_id == trace_id))
                trace = existing.scalar_one_or_none()
                if trace:
                    return trace

                trace = TraceModel(task_id=task_id, trace_id=trace_id, user_id=user_id, status=status)
                session.add(trace)
                await session.commit()
                await session.refresh(trace)
                return trace
        except Exception as e:
            _fallback_log("TraceRepository.create", e)
            row = _memory_row(id=trace_id, task_id=task_id, trace_id=trace_id, user_id=user_id, status=status, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            _MEMORY_TRACES[trace_id] = row
            return row

    async def get_by_task(self, task_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(TraceModel).where(TraceModel.task_id == task_id))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("TraceRepository.get_by_task", e)
            return [trace for trace in _MEMORY_TRACES.values() if trace.task_id == task_id]

    async def get_by_trace_id(self, trace_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(TraceModel).where(TraceModel.trace_id == trace_id))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("TraceRepository.get_by_trace_id", e)
            return _MEMORY_TRACES.get(trace_id)

    async def update_status(self, trace_id: str, status: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(TraceModel).where(TraceModel.trace_id == trace_id))
                trace = result.scalar_one_or_none()
                if trace:
                    trace.status = status
                    await session.commit()
                    await session.refresh(trace)
                return trace
        except Exception as e:
            _fallback_log("TraceRepository.update_status", e)
            trace = _MEMORY_TRACES.get(trace_id)
            if trace:
                trace.status = status
                trace.updated_at = datetime.utcnow()
            return trace


class NodeTraceRepository:
    async def create(
        self,
        task_id: str,
        user_id: str,
        trace_id: str,
        node_id: str,
        status: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        try:
            async with db.get_session() as session:
                row = NodeTraceModel(
                    task_id=task_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    node_id=node_id,
                    status=status,
                    input_data=input_data,
                    output_data=output_data,
                    error=error,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return row
        except Exception as e:
            _fallback_log("NodeTraceRepository.create", e)
            row = _memory_row(
                id=str(uuid4()),
                task_id=task_id,
                user_id=user_id,
                trace_id=trace_id,
                node_id=node_id,
                status=status,
                input_data=input_data or {},
                output_data=output_data,
                error=error,
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            _MEMORY_NODE_TRACES[row.id] = row
            return row

    async def update(
        self,
        node_trace_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(NodeTraceModel).where(NodeTraceModel.id == node_trace_id))
                row = result.scalar_one_or_none()
                if row:
                    if status:
                        row.status = status
                    if output_data is not None:
                        row.output_data = output_data
                    if error is not None:
                        row.error = error
                    row.finished_at = datetime.utcnow()
                    await session.commit()
                    await session.refresh(row)
                return row
        except Exception as e:
            _fallback_log("NodeTraceRepository.update", e)
            row = _MEMORY_NODE_TRACES.get(node_trace_id)
            if row:
                if status:
                    row.status = status
                if output_data is not None:
                    row.output_data = output_data
                if error is not None:
                    row.error = error
                row.finished_at = datetime.utcnow()
                row.updated_at = datetime.utcnow()
            return row

    async def get_by_task(self, task_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(NodeTraceModel).where(NodeTraceModel.task_id == task_id).order_by(NodeTraceModel.created_at))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("NodeTraceRepository.get_by_task", e)
            return [row for row in _MEMORY_NODE_TRACES.values() if row.task_id == task_id]


class SpanRepository:
    async def create(
        self,
        trace_id: str,
        span_id: str,
        operation: str,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        try:
            async with db.get_session() as session:
                span = SpanModel(trace_id=trace_id, span_id=span_id, operation=operation, agent_name=agent_name, metadata_json=metadata)
                session.add(span)
                await session.commit()
                await session.refresh(span)
                return span
        except Exception as e:
            _fallback_log("SpanRepository.create", e)
            row = _memory_row(
                id=span_id,
                trace_id=trace_id,
                span_id=span_id,
                operation=operation,
                agent_name=agent_name,
                status="pending",
                error=None,
                metadata=metadata or {},
                start_time=datetime.utcnow(),
                end_time=None,
            )
            _MEMORY_SPANS[span_id] = row
            return row

    async def update(self, span_id: str, status: str, error: Optional[str] = None):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(SpanModel).where(SpanModel.span_id == span_id))
                span = result.scalar_one_or_none()
                if span:
                    span.status = status
                    span.error = error
                    span.end_time = datetime.utcnow()
                    await session.commit()
                    await session.refresh(span)
                return span
        except Exception as e:
            _fallback_log("SpanRepository.update", e)
            span = _MEMORY_SPANS.get(span_id)
            if span:
                span.status = status
                span.error = error
                span.end_time = datetime.utcnow()
            return span

    async def get_by_trace(self, trace_id: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(SpanModel).where(SpanModel.trace_id == trace_id))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("SpanRepository.get_by_trace", e)
            return [span for span in _MEMORY_SPANS.values() if getattr(span, "trace_id", None) == trace_id]


class ToolRepository:
    async def upsert(
        self,
        name: str,
        description: str,
        tool_type: str = "custom",
        parameters_schema: Optional[Dict[str, Any]] = None,
        template: Optional[str] = None,
        status: str = "active",
    ):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(ToolModel).where(ToolModel.name == name))
                tool = result.scalar_one_or_none()
                if not tool:
                    tool = ToolModel(name=name, description=description, type=tool_type, parameters_schema=parameters_schema, template=template, status=status)
                    session.add(tool)
                else:
                    tool.description = description
                    tool.type = tool_type
                    tool.parameters_schema = parameters_schema
                    tool.template = template
                    tool.status = status
                await session.commit()
                await session.refresh(tool)
                return tool
        except Exception as e:
            _fallback_log("ToolRepository.upsert", e)
            row = _memory_row(name=name, description=description, type=tool_type, parameters_schema=parameters_schema or {}, template=template, status=status)
            _MEMORY_TOOLS[name] = row
            return row

    async def list_all(self):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(ToolModel).order_by(ToolModel.created_at.desc()))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("ToolRepository.list_all", e)
            return list(_MEMORY_TOOLS.values())

    async def get_by_name(self, name: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(ToolModel).where(ToolModel.name == name))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("ToolRepository.get_by_name", e)
            return _MEMORY_TOOLS.get(name)


class AgentRepository:
    async def upsert(
        self,
        agent_key: str,
        name: str,
        role: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[str]] = None,
        status: str = "active",
    ):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(AgentModel).where(AgentModel.agent_key == agent_key))
                agent = result.scalar_one_or_none()
                if not agent:
                    agent = AgentModel(agent_key=agent_key, name=name, role=role, system_prompt=system_prompt, model=model, temperature=temperature, max_tokens=max_tokens, tools=tools, status=status)
                    session.add(agent)
                else:
                    agent.name = name
                    agent.role = role
                    agent.system_prompt = system_prompt
                    agent.model = model
                    agent.temperature = temperature
                    agent.max_tokens = max_tokens
                    agent.tools = tools
                    agent.status = status
                await session.commit()
                await session.refresh(agent)
                return agent
        except Exception as e:
            _fallback_log("AgentRepository.upsert", e)
            row = _memory_row(
                agent_key=agent_key,
                name=name,
                role=role,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools or [],
                status=status,
                created_at=datetime.utcnow(),
            )
            _MEMORY_AGENTS[agent_key] = row
            return row

    async def delete(self, agent_key: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(AgentModel).where(AgentModel.agent_key == agent_key))
                agent = result.scalar_one_or_none()
                if agent:
                    await session.delete(agent)
                    await session.commit()
                return agent
        except Exception as e:
            _fallback_log("AgentRepository.delete", e)
            return _MEMORY_AGENTS.pop(agent_key, None)

    async def get_by_agent_key(self, agent_key: str):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(AgentModel).where(AgentModel.agent_key == agent_key))
                return result.scalar_one_or_none()
        except Exception as e:
            _fallback_log("AgentRepository.get_by_agent_key", e)
            return _MEMORY_AGENTS.get(agent_key)

    async def list_all(self):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(AgentModel).order_by(AgentModel.created_at.desc()))
                return result.scalars().all()
        except Exception as e:
            _fallback_log("AgentRepository.list_all", e)
            return list(_MEMORY_AGENTS.values())


class ConfigRepository:
    async def get_all(self):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(ConfigModel))
                rows = result.scalars().all()
                return {row.key: row.value for row in rows}
        except Exception as e:
            _fallback_log("ConfigRepository.get_all", e)
            return dict(_MEMORY_CONFIG)

    async def upsert(self, key: str, value: Any):
        try:
            async with db.get_session() as session:
                result = await session.execute(select(ConfigModel).where(ConfigModel.key == key))
                item = result.scalar_one_or_none()
                if not item:
                    item = ConfigModel(key=key, value=value)
                    session.add(item)
                else:
                    item.value = value
                await session.commit()
                await session.refresh(item)
                return item
        except Exception as e:
            _fallback_log("ConfigRepository.upsert", e)
            _MEMORY_CONFIG[key] = value
            return _memory_row(key=key, value=value)

    async def reset(self, defaults: Dict[str, Any]):
        try:
            async with db.get_session() as session:
                await session.execute(ConfigModel.__table__.delete())
                for key, value in defaults.items():
                    session.add(ConfigModel(key=key, value=value))
                await session.commit()
                return defaults
        except Exception as e:
            _fallback_log("ConfigRepository.reset", e)
            _MEMORY_CONFIG.clear()
            _MEMORY_CONFIG.update(defaults)
            return defaults


trace_repo = TraceRepository()
node_trace_repo = NodeTraceRepository()
span_repo = SpanRepository()
tool_repo = ToolRepository()
agent_repo = AgentRepository()
config_repo = ConfigRepository()
