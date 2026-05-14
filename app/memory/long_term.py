import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from .models import (
    TaskModel,
    WorkflowModel,
    WorkflowNodeModel,
    WorkflowEdgeModel,
    UserModel,
    TraceModel,
    NodeTraceModel,
    SpanModel,
    TokenUsageModel,
    ToolModel,
    MCPServerModel,
    AgentModel,
    AgentVersionModel,
    ConfigModel,
    GuardrailRuleModel,
    CheckpointModel,
    DeploymentModel,
)
from ..config.settings import settings
from ..logs.logger import logger

DATABASE_URL = settings.DATABASE_URL


class Database:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._loop = None

    async def connect(self):
        current_loop = asyncio.get_running_loop()
        if self.engine is not None and self._loop is current_loop:
            return
        if self.engine is not None:
            await self.engine.dispose()
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        engine_kwargs = {
            "echo": False,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
        }
        if not DATABASE_URL.startswith("sqlite"):
            engine_kwargs.update({
                "pool_size": 20,
                "max_overflow": 40,
                "pool_timeout": 30,
            })
        self.engine = create_async_engine(
            DATABASE_URL,
            **engine_kwargs,
        )
        self.session_factory = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self._loop = current_loop
        logger.info("Database engine connected (schema managed by migrations)")

    async def disconnect(self):
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            self._loop = None
            logger.info("Database disconnected")

    def get_session(self) -> AsyncSession:
        if not self.session_factory:
            raise RuntimeError("Database session factory is unavailable")
        return self.session_factory()

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope around a series of operations.

        Use this when you need to group multiple repository calls or raw
        operations into a single database transaction with automatic
        rollback on failure.

        Usage:
            async with db.session_scope() as session:
                task = await task_repo.create(...)
                await trace_repo.create(...)
                # Both succeed or both roll back

        NOTE: Each repository method (e.g. TaskRepository.get()) currently
        opens its own session. For simple reads this is fine — but when you
        need atomicity across multiple operations, wrap them in this scope
        instead of calling individual repo methods.
        """
        session = self.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


db = Database()


class TaskRepository:
    async def create(self, task_id: str, query: str, user_id: str = "system", status: str = "pending") -> TaskModel:
        async with db.get_session() as session:
            task = TaskModel(id=task_id, query=query, user_id=user_id, status=status)
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    async def get(self, task_id: str) -> Optional[TaskModel]:
        async with db.get_session() as session:
            result = await session.execute(select(TaskModel).where(TaskModel.id == task_id))
            return result.scalar_one_or_none()

    async def update(
        self,
        task_id: str,
        status: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskModel]:
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

    async def list_all(self) -> List[TaskModel]:
        async with db.get_session() as session:
            result = await session.execute(select(TaskModel).order_by(TaskModel.created_at.desc()))
            return result.scalars().all()

    async def list_by_user(self, user_id: str, limit: int = 50, offset: int = 0) -> List[TaskModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(TaskModel)
                .where(TaskModel.user_id == user_id)
                .order_by(TaskModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

    async def count_active_by_user(self, user_id: str) -> int:
        from sqlalchemy import func
        async with db.get_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(TaskModel)
                .where(TaskModel.user_id == user_id)
                .where(TaskModel.status.in_(["pending", "running"]))
            )
            return result.scalar() or 0


class WorkflowRepository:
    async def create(
        self,
        task_id: str,
        user_id: str = "system",
        name: Optional[str] = None,
        definition: Optional[Dict[str, Any]] = None,
        status: str = "pending",
    ) -> WorkflowModel:
        async with db.get_session() as session:
            workflow = WorkflowModel(task_id=task_id, user_id=user_id, name=name, definition=definition, status=status)
            session.add(workflow)
            await session.commit()
            await session.refresh(workflow)
            return workflow

    async def get_by_id(self, workflow_id: str) -> Optional[WorkflowModel]:
        async with db.get_session() as session:
            result = await session.execute(select(WorkflowModel).where(WorkflowModel.id == workflow_id))
            return result.scalar_one_or_none()

    async def get_by_task(self, task_id: str) -> Optional[WorkflowModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(WorkflowModel)
                .where(WorkflowModel.task_id == task_id)
                .order_by(WorkflowModel.created_at.desc())
            )
            rows = result.scalars().all()
            return rows[0] if rows else None

    async def get_by_task_ids(self, task_ids: List[str]) -> List[WorkflowModel]:
        async with db.get_session() as session:
            result = await session.execute(select(WorkflowModel).where(WorkflowModel.task_id.in_(task_ids)))
            return result.scalars().all()

    async def list_by_user(self, user_id: str) -> List[WorkflowModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(WorkflowModel)
                .where(WorkflowModel.user_id == user_id)
                .order_by(WorkflowModel.created_at.desc())
            )
            return result.scalars().all()

    async def update(
        self,
        workflow_id: str,
        definition: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> Optional[WorkflowModel]:
        async with db.get_session() as session:
            result = await session.execute(select(WorkflowModel).where(WorkflowModel.id == workflow_id))
            workflow = result.scalar_one_or_none()
            if workflow:
                if definition is not None:
                    workflow.definition = definition
                if status:
                    workflow.status = status
                await session.commit()
                await session.refresh(workflow)
            return workflow


class WorkflowNodeRepository:
    async def create(
        self,
        workflow_id: str,
        step_number: int,
        agent_type: str,
        depends_on: Optional[List[int]] = None,
        input_data: Optional[Dict[str, Any]] = None,
        condition_code: Optional[str] = None,
        node_type: str = "agent",
        approval_config: Optional[Dict[str, Any]] = None,
    ) -> WorkflowNodeModel:
        async with db.get_session() as session:
            node = WorkflowNodeModel(
                workflow_id=workflow_id,
                step_number=step_number,
                agent_type=agent_type,
                depends_on=depends_on or [],
                input_data=input_data,
                condition_code=condition_code,
                node_type=node_type,
                approval_config=approval_config,
            )
            session.add(node)
            await session.commit()
            await session.refresh(node)
            return node

    async def bulk_create(
        self,
        nodes: List[Dict[str, Any]]
    ) -> List[WorkflowNodeModel]:
        async with db.get_session() as session:
            created = []
            for node_data in nodes:
                node = WorkflowNodeModel(**node_data)
                session.add(node)
                created.append(node)
            await session.commit()
            for node in created:
                await session.refresh(node)
            return created

    async def update(
        self,
        node_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ):
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

    async def get_by_id(self, node_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(WorkflowNodeModel).where(WorkflowNodeModel.id == node_id))
            return result.scalar_one_or_none()

    async def get_by_workflow(self, workflow_id: str):
        async with db.get_session() as session:
            result = await session.execute(
                select(WorkflowNodeModel).where(WorkflowNodeModel.workflow_id == workflow_id).order_by(WorkflowNodeModel.step_number)
            )
            return result.scalars().all()

    async def get_by_workflow_ids(self, workflow_ids: List[str]):
        async with db.get_session() as session:
            result = await session.execute(
                select(WorkflowNodeModel).where(WorkflowNodeModel.workflow_id.in_(workflow_ids)).order_by(WorkflowNodeModel.step_number)
            )
            return result.scalars().all()

    async def delete_by_workflow(self, workflow_id: str) -> int:
        async with db.get_session() as session:
            result = await session.execute(
                select(WorkflowNodeModel).where(WorkflowNodeModel.workflow_id == workflow_id)
            )
            nodes = result.scalars().all()
            for node in nodes:
                await session.delete(node)
            await session.commit()
            return len(nodes)


class WorkflowEdgeRepository:
    async def create(self, workflow_id: str, from_node_id: str, to_node_id: str) -> WorkflowEdgeModel:
        async with db.get_session() as session:
            edge = WorkflowEdgeModel(workflow_id=workflow_id, from_node_id=from_node_id, to_node_id=to_node_id)
            session.add(edge)
            await session.commit()
            await session.refresh(edge)
            return edge

    async def bulk_create(self, edges: List[Dict[str, Any]]) -> List[WorkflowEdgeModel]:
        async with db.get_session() as session:
            created = []
            for edge_data in edges:
                edge = WorkflowEdgeModel(**edge_data)
                session.add(edge)
                created.append(edge)
            await session.commit()
            for edge in created:
                await session.refresh(edge)
            return created

    async def get_by_workflow(self, workflow_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_id == workflow_id))
            return result.scalars().all()

    async def delete_by_workflow(self, workflow_id: str) -> int:
        async with db.get_session() as session:
            result = await session.execute(
                select(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_id == workflow_id)
            )
            edges = result.scalars().all()
            for edge in edges:
                await session.delete(edge)
            await session.commit()
            return len(edges)

    async def get_by_workflow_ids(self, workflow_ids: List[str]):
        async with db.get_session() as session:
            result = await session.execute(select(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_id.in_(workflow_ids)))
            return result.scalars().all()


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
        async with db.get_session() as session:
            user = UserModel(id=user_id, email=email, hashed_password=hashed_password, name=name, api_key=api_key, role=role)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        async with db.get_session() as session:
            result = await session.execute(select(UserModel).where(UserModel.email == email))
            return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> Optional[UserModel]:
        async with db.get_session() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            return result.scalar_one_or_none()

    async def get_by_api_key(self, api_key: str) -> Optional[UserModel]:
        async with db.get_session() as session:
            result = await session.execute(select(UserModel).where(UserModel.api_key == api_key))
            return result.scalar_one_or_none()

    async def update_api_key(self, user_id: str, api_key: str) -> Optional[UserModel]:
        async with db.get_session() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.api_key = api_key
                await session.commit()
                await session.refresh(user)
            return user


class TraceRepository:
    async def create(self, task_id: str, trace_id: str, user_id: str, status: str = "pending"):
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

    async def get_by_task(self, task_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(TraceModel).where(TraceModel.task_id == task_id))
            return result.scalars().all()

    async def get_by_trace_id(self, trace_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(TraceModel).where(TraceModel.trace_id == trace_id))
            return result.scalar_one_or_none()

    async def update_status(self, trace_id: str, status: str):
        async with db.get_session() as session:
            result = await session.execute(select(TraceModel).where(TraceModel.trace_id == trace_id))
            trace = result.scalar_one_or_none()
            if trace:
                trace.status = status
                await session.commit()
                await session.refresh(trace)
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

    async def update(
        self,
        node_trace_id: str,
        status: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
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
                row.finished_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(row)
            return row

    async def get_by_task(self, task_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(NodeTraceModel).where(NodeTraceModel.task_id == task_id).order_by(NodeTraceModel.created_at))
            return result.scalars().all()


class SpanRepository:
    async def create(
        self,
        trace_id: str,
        span_id: str,
        operation: str,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        async with db.get_session() as session:
            existing = await session.execute(select(SpanModel).where(SpanModel.span_id == span_id))
            span = existing.scalar_one_or_none()
            if span:
                return span
            span = SpanModel(trace_id=trace_id, span_id=span_id, operation=operation, agent_name=agent_name, metadata_json=metadata)
            session.add(span)
            await session.commit()
            await session.refresh(span)
            return span

    async def update(self, span_id: str, status: str, error: Optional[str] = None):
        async with db.get_session() as session:
            result = await session.execute(select(SpanModel).where(SpanModel.span_id == span_id))
            span = result.scalar_one_or_none()
            if span:
                span.status = status
                span.error = error
                span.end_time = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(span)
            return span

    async def get_by_trace(self, trace_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(SpanModel).where(SpanModel.trace_id == trace_id))
            return result.scalars().all()


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

    async def list_all(self):
        async with db.get_session() as session:
            result = await session.execute(select(ToolModel).order_by(ToolModel.created_at.desc()))
            return result.scalars().all()

    async def get_by_name(self, name: str):
        async with db.get_session() as session:
            result = await session.execute(select(ToolModel).where(ToolModel.name == name))
            return result.scalar_one_or_none()


class MCPServerRepository:
    async def create(
        self,
        name: str,
        endpoint: str,
        tools_list: Optional[List[Dict[str, Any]]] = None,
        auth_scope: Optional[str] = None,
        health_status: str = "unknown",
        version: str = "1.0.0",
        status: str = "active",
    ):
        async with db.get_session() as session:
            existing = await session.execute(select(MCPServerModel).where(MCPServerModel.name == name))
            if existing.scalar_one_or_none():
                raise ValueError(f"MCP server '{name}' already exists")
            server = MCPServerModel(
                name=name, endpoint=endpoint, tools_list=tools_list,
                auth_scope=auth_scope, health_status=health_status,
                version=version, status=status,
            )
            session.add(server)
            await session.commit()
            await session.refresh(server)
            return server

    async def update(
        self,
        server_id: str,
        endpoint: Optional[str] = None,
        tools_list: Optional[List[Dict[str, Any]]] = None,
        auth_scope: Optional[str] = None,
        health_status: Optional[str] = None,
        version: Optional[str] = None,
        status: Optional[str] = None,
    ):
        async with db.get_session() as session:
            result = await session.execute(select(MCPServerModel).where(MCPServerModel.id == server_id))
            server = result.scalar_one_or_none()
            if not server:
                return None
            if endpoint is not None:
                server.endpoint = endpoint
            if tools_list is not None:
                server.tools_list = tools_list
            if auth_scope is not None:
                server.auth_scope = auth_scope
            if health_status is not None:
                server.health_status = health_status
            if version is not None:
                server.version = version
            if status is not None:
                server.status = status
            await session.commit()
            await session.refresh(server)
            return server

    async def get_by_name(self, name: str):
        async with db.get_session() as session:
            result = await session.execute(select(MCPServerModel).where(MCPServerModel.name == name))
            return result.scalar_one_or_none()

    async def list_all(self):
        async with db.get_session() as session:
            result = await session.execute(select(MCPServerModel).order_by(MCPServerModel.created_at.desc()))
            return result.scalars().all()

    async def delete(self, server_id: str):
        async with db.get_session() as session:
            result = await session.execute(select(MCPServerModel).where(MCPServerModel.id == server_id))
            server = result.scalar_one_or_none()
            if server:
                await session.delete(server)
                await session.commit()
            return server


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
        version: Optional[str] = None,
        status: str = "active",
    ):
        async with db.get_session() as session:
            result = await session.execute(select(AgentModel).where(AgentModel.agent_key == agent_key))
            agent = result.scalar_one_or_none()
            if not agent:
                agent = AgentModel(
                    agent_key=agent_key, name=name, role=role,
                    system_prompt=system_prompt, model=model,
                    temperature=temperature, max_tokens=max_tokens,
                    tools=tools, version=version or "1.0.0",
                    status=status,
                )
                session.add(agent)
            else:
                agent.name = name
                agent.role = role
                agent.system_prompt = system_prompt
                agent.model = model
                agent.temperature = temperature
                agent.max_tokens = max_tokens
                agent.tools = tools
                if version:
                    agent.version = version
                agent.status = status
            await session.commit()
            await session.refresh(agent)
            return agent

    async def delete(self, agent_key: str):
        async with db.get_session() as session:
            result = await session.execute(select(AgentModel).where(AgentModel.agent_key == agent_key))
            agent = result.scalar_one_or_none()
            if agent:
                await session.delete(agent)
                await session.commit()
            return agent

    async def get_by_agent_key(self, agent_key: str):
        async with db.get_session() as session:
            result = await session.execute(select(AgentModel).where(AgentModel.agent_key == agent_key))
            return result.scalar_one_or_none()

    async def list_all(self):
        async with db.get_session() as session:
            result = await session.execute(select(AgentModel).order_by(AgentModel.created_at.desc()))
            return result.scalars().all()

    async def list_versions(self, agent_key: str):
        async with db.get_session() as session:
            result = await session.execute(
                select(AgentVersionModel)
                .where(AgentVersionModel.agent_key == agent_key)
                .order_by(AgentVersionModel.created_at.desc())
            )
            return result.scalars().all()

    async def get_version(self, agent_key: str, version: str):
        async with db.get_session() as session:
            result = await session.execute(
                select(AgentVersionModel)
                .where(AgentVersionModel.agent_key == agent_key)
                .where(AgentVersionModel.version == version)
            )
            return result.scalar_one_or_none()

    async def create_version(
        self,
        agent_key: str,
        version: str,
        name: str,
        role: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[str]] = None,
    ):
        async with db.get_session() as session:
            existing = await session.execute(
                select(AgentVersionModel)
                .where(AgentVersionModel.agent_key == agent_key)
                .where(AgentVersionModel.version == version)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Version {version} already exists for agent {agent_key}")
            v = AgentVersionModel(
                agent_key=agent_key, version=version, name=name, role=role,
                system_prompt=system_prompt, model=model,
                temperature=temperature, max_tokens=max_tokens,
                tools=tools,
            )
            session.add(v)
            await session.commit()
            await session.refresh(v)
            return v


class MessageRepository:
    async def create(
        self,
        task_id: str,
        step_id: Optional[str] = None,
        sender: str = "system",
        receiver: str = "system",
        payload: Optional[Dict[str, Any]] = None,
    ):
        async with db.get_session() as session:
            msg = MessageModel(
                task_id=task_id,
                step_id=step_id,
                sender=sender,
                receiver=receiver,
                payload=payload,
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)
            return msg

    async def get_by_task(self, task_id: str):
        async with db.get_session() as session:
            result = await session.execute(
                select(MessageModel).where(MessageModel.task_id == task_id).order_by(MessageModel.created_at)
            )
            return result.scalars().all()


class ConfigRepository:
    async def get_all(self):
        async with db.get_session() as session:
            result = await session.execute(select(ConfigModel))
            rows = result.scalars().all()
            return {row.key: row.value for row in rows}

    async def upsert(self, key: str, value: Any):
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

    async def get(self, key: str):
        async with db.get_session() as session:
            result = await session.execute(select(ConfigModel).where(ConfigModel.key == key))
            item = result.scalar_one_or_none()
            return item.value if item else None

    async def reset(self, defaults: Dict[str, Any]):
        async with db.get_session() as session:
            await session.execute(ConfigModel.__table__.delete())
            for key, value in defaults.items():
                session.add(ConfigModel(key=key, value=value))
            await session.commit()
            return defaults


class DeploymentRepository:
    async def create(
        self,
        user_id: str,
        workflow_id: str,
        name: str,
        endpoint_path: str,
        auth_type: str = "none",
        api_key_hash: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "active",
    ) -> DeploymentModel:
        async with db.get_session() as session:
            deployment = DeploymentModel(
                user_id=user_id,
                workflow_id=workflow_id,
                name=name,
                endpoint_path=endpoint_path,
                auth_type=auth_type,
                api_key_hash=api_key_hash,
                description=description,
                status=status,
            )
            session.add(deployment)
            await session.commit()
            await session.refresh(deployment)
            return deployment

    async def get_by_id(self, deployment_id: str) -> Optional[DeploymentModel]:
        async with db.get_session() as session:
            result = await session.execute(select(DeploymentModel).where(DeploymentModel.id == deployment_id))
            return result.scalar_one_or_none()

    async def get_by_path(self, endpoint_path: str) -> Optional[DeploymentModel]:
        async with db.get_session() as session:
            result = await session.execute(select(DeploymentModel).where(DeploymentModel.endpoint_path == endpoint_path))
            return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> List[DeploymentModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(DeploymentModel)
                .where(DeploymentModel.user_id == user_id)
                .order_by(DeploymentModel.created_at.desc())
            )
            return result.scalars().all()

    async def update_status(self, deployment_id: str, status: str) -> Optional[DeploymentModel]:
        async with db.get_session() as session:
            result = await session.execute(select(DeploymentModel).where(DeploymentModel.id == deployment_id))
            deployment = result.scalar_one_or_none()
            if deployment:
                deployment.status = status
                await session.commit()
                await session.refresh(deployment)
            return deployment

    async def delete(self, deployment_id: str) -> Optional[DeploymentModel]:
        async with db.get_session() as session:
            result = await session.execute(select(DeploymentModel).where(DeploymentModel.id == deployment_id))
            deployment = result.scalar_one_or_none()
            if deployment:
                await session.delete(deployment)
                await session.commit()
            return deployment


class GuardrailRuleRepository:
    async def create(
        self,
        name: str,
        rule_type: str,
        condition: Dict[str, Any],
        action: str = "block",
        status: str = "active",
    ) -> GuardrailRuleModel:
        async with db.get_session() as session:
            rule = GuardrailRuleModel(
                name=name,
                rule_type=rule_type,
                condition=condition,
                action=action,
                status=status,
            )
            session.add(rule)
            await session.commit()
            await session.refresh(rule)
            return rule

    async def list_active(self) -> List[GuardrailRuleModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(GuardrailRuleModel).where(GuardrailRuleModel.status == "active")
            )
            return result.scalars().all()

    async def get_by_name(self, name: str) -> Optional[GuardrailRuleModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(GuardrailRuleModel).where(GuardrailRuleModel.name == name)
            )
            return result.scalar_one_or_none()

    async def update_status(self, rule_id: str, status: str) -> Optional[GuardrailRuleModel]:
        async with db.get_session() as session:
            result = await session.execute(
                select(GuardrailRuleModel).where(GuardrailRuleModel.id == rule_id)
            )
            rule = result.scalar_one_or_none()
            if rule:
                rule.status = status
                await session.commit()
                await session.refresh(rule)
            return rule


class TokenUsageRepository:
    async def create(
        self,
        task_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cost_usd: float,
    ) -> TokenUsageModel:
        async with db.get_session() as session:
            usage = TokenUsageModel(
                task_id=task_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            )
            session.add(usage)
            await session.commit()
            await session.refresh(usage)
            return usage

    async def get_total_tokens(self) -> int:
        from sqlalchemy import func
        async with db.get_session() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(TokenUsageModel.total_tokens), 0))
            )
            return result.scalar() or 0

    async def get_total_tokens_today(self) -> int:
        from sqlalchemy import func
        async with db.get_session() as session:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            result = await session.execute(
                select(func.coalesce(func.sum(TokenUsageModel.total_tokens), 0))
                .where(TokenUsageModel.created_at >= today_start)
            )
            return result.scalar() or 0

    async def get_usage_by_model(self, limit: int = 10):
        from sqlalchemy import func
        async with db.get_session() as session:
            result = await session.execute(
                select(TokenUsageModel.model, func.sum(TokenUsageModel.total_tokens))
                .group_by(TokenUsageModel.model)
                .order_by(func.sum(TokenUsageModel.total_tokens).desc())
                .limit(limit)
            )
            return result.all()


task_repo = TaskRepository()
workflow_repo = WorkflowRepository()
workflow_node_repo = WorkflowNodeRepository()
workflow_edge_repo = WorkflowEdgeRepository()
user_repo = UserRepository()
trace_repo = TraceRepository()
node_trace_repo = NodeTraceRepository()
span_repo = SpanRepository()
token_usage_repo = TokenUsageRepository()
tool_repo = ToolRepository()
mcp_server_repo = MCPServerRepository()
agent_repo = AgentRepository()
message_repo = MessageRepository()
config_repo = ConfigRepository()
deployment_repo = DeploymentRepository()
guardrail_rule_repo = GuardrailRuleRepository()
