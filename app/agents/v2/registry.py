from typing import Dict, Optional, List
from sqlalchemy import select
from ...memory.models import AgentConfigV2Model
from ...memory.long_term import db
from .schemas import AgentConfigV2, AgentToolBinding
from ...logs.logger import logger


class AgentRegistryV2:
    def __init__(self):
        self._cache: Dict[str, AgentConfigV2] = {}

    def _row_to_schema(self, row: AgentConfigV2Model) -> AgentConfigV2:
        return AgentConfigV2(
            agent_id=row.agent_id,
            name=row.name,
            role=row.role,
            goal=row.goal or "",
            backstory=row.backstory or "",
            model=row.model or "gpt-4o",
            temperature=row.temperature if row.temperature is not None else 0.7,
            max_tokens=row.max_tokens if row.max_tokens is not None else 2048,
            reasoning=row.reasoning if row.reasoning is not None else False,
            max_reasoning_attempts=row.max_reasoning_attempts if row.max_reasoning_attempts is not None else 3,
            tools=[AgentToolBinding(**t) for t in (row.tools or [])],
            allow_delegation=row.allow_delegation if row.allow_delegation is not None else False,
            memory_enabled=row.memory_enabled if row.memory_enabled is not None else True,
            knowledge_sources=row.knowledge_sources or [],
            max_iter=row.max_iter if row.max_iter is not None else 20,
            max_execution_time=row.max_execution_time if row.max_execution_time is not None else 300,
            max_retry_limit=row.max_retry_limit if row.max_retry_limit is not None else 2,
            system_template=row.system_template,
            prompt_template=row.prompt_template,
            response_template=row.response_template,
        )

    async def register(self, config: AgentConfigV2) -> AgentConfigV2:
        async with db.get_session() as session:
            result = await session.execute(
                select(AgentConfigV2Model).where(AgentConfigV2Model.agent_id == config.agent_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.name = config.name
                row.role = config.role
                row.goal = config.goal
                row.backstory = config.backstory
                row.model = config.model
                row.temperature = config.temperature
                row.max_tokens = config.max_tokens
                row.reasoning = config.reasoning
                row.max_reasoning_attempts = config.max_reasoning_attempts
                row.tools = [t.model_dump() for t in config.tools]
                row.allow_delegation = config.allow_delegation
                row.memory_enabled = config.memory_enabled
                row.knowledge_sources = config.knowledge_sources
                row.max_iter = config.max_iter
                row.max_execution_time = config.max_execution_time
                row.max_retry_limit = config.max_retry_limit
                row.system_template = config.system_template
                row.prompt_template = config.prompt_template
                row.response_template = config.response_template
                row.status = "active"
            else:
                row = AgentConfigV2Model(
                    agent_id=config.agent_id,
                    name=config.name,
                    role=config.role,
                    goal=config.goal,
                    backstory=config.backstory,
                    model=config.model,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    reasoning=config.reasoning,
                    max_reasoning_attempts=config.max_reasoning_attempts,
                    tools=[t.model_dump() for t in config.tools],
                    allow_delegation=config.allow_delegation,
                    memory_enabled=config.memory_enabled,
                    knowledge_sources=config.knowledge_sources,
                    max_iter=config.max_iter,
                    max_execution_time=config.max_execution_time,
                    max_retry_limit=config.max_retry_limit,
                    system_template=config.system_template,
                    prompt_template=config.prompt_template,
                    response_template=config.response_template,
                    status="active",
                )
                session.add(row)
            await session.commit()
            await session.refresh(row)
            schema = self._row_to_schema(row)
            self._cache[config.agent_id] = schema
            return schema

    async def get(self, agent_id: str) -> Optional[AgentConfigV2]:
        if agent_id in self._cache:
            return self._cache[agent_id]
        async with db.get_session() as session:
            result = await session.execute(
                select(AgentConfigV2Model).where(AgentConfigV2Model.agent_id == agent_id)
            )
            row = result.scalar_one_or_none()
            if row:
                schema = self._row_to_schema(row)
                self._cache[agent_id] = schema
                return schema
            return None

    async def list_all(self) -> List[AgentConfigV2]:
        async with db.get_session() as session:
            result = await session.execute(
                select(AgentConfigV2Model).where(AgentConfigV2Model.status == "active")
            )
            rows = result.scalars().all()
            return [self._row_to_schema(row) for row in rows]

    async def delete(self, agent_id: str) -> Optional[AgentConfigV2]:
        async with db.get_session() as session:
            result = await session.execute(
                select(AgentConfigV2Model).where(AgentConfigV2Model.agent_id == agent_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.status = "deleted"
                await session.commit()
                await session.refresh(row)
                if agent_id in self._cache:
                    del self._cache[agent_id]
                return self._row_to_schema(row)
            return None


agent_registry_v2 = AgentRegistryV2()
