from typing import Dict, Optional, List
from sqlalchemy import select
from ...memory.models import ToolV2Model
from ...memory.long_term import db
from .schemas import ToolV2, ToolImplementation, ImplementationType, HealthMetrics
from ...logs.logger import logger


class ToolRegistryV2:
    def __init__(self):
        self._cache: Dict[str, ToolV2] = {}

    def _row_to_schema(self, row: ToolV2Model) -> ToolV2:
        return ToolV2(
            tool_id=row.tool_id,
            name=row.name,
            description=row.description,
            version=row.version or "1.0.0",
            input_schema=row.input_schema or {},
            output_schema=row.output_schema,
            implementation=ToolImplementation(
                type=ImplementationType(row.implementation_type),
                config=row.implementation_config or {},
            ),
            category=row.category or "general",
            tags=row.tags or [],
            author=row.author or "system",
            dependencies=row.dependencies or [],
            sandboxed=row.sandboxed if row.sandboxed is not None else False,
            timeout=row.timeout if row.timeout is not None else 30,
            max_retries=row.max_retries if row.max_retries is not None else 2,
            health=HealthMetrics(
                invocation_count=row.invocation_count or 0,
                avg_latency_ms=row.avg_latency_ms or 0.0,
                error_rate=row.error_rate or 0.0,
                last_check=None,
            ),
        )

    async def register(self, tool: ToolV2) -> ToolV2:
        async with db.get_session() as session:
            result = await session.execute(
                select(ToolV2Model).where(ToolV2Model.tool_id == tool.tool_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.name = tool.name
                row.description = tool.description
                row.version = tool.version
                row.input_schema = tool.input_schema
                row.output_schema = tool.output_schema
                row.implementation_type = tool.implementation.type.value
                row.implementation_config = tool.implementation.config
                row.category = tool.category
                row.tags = tool.tags
                row.author = tool.author
                row.dependencies = tool.dependencies
                row.sandboxed = tool.sandboxed
                row.timeout = tool.timeout
                row.max_retries = tool.max_retries
            else:
                row = ToolV2Model(
                    tool_id=tool.tool_id,
                    name=tool.name,
                    description=tool.description,
                    version=tool.version,
                    input_schema=tool.input_schema,
                    output_schema=tool.output_schema,
                    implementation_type=tool.implementation.type.value,
                    implementation_config=tool.implementation.config,
                    category=tool.category,
                    tags=tool.tags,
                    author=tool.author,
                    dependencies=tool.dependencies,
                    sandboxed=tool.sandboxed,
                    timeout=tool.timeout,
                    max_retries=tool.max_retries,
                )
                session.add(row)
            await session.commit()
            await session.refresh(row)
            schema = self._row_to_schema(row)
            self._cache[tool.tool_id] = schema
            return schema

    async def get(self, tool_id: str) -> Optional[ToolV2]:
        if tool_id in self._cache:
            return self._cache[tool_id]
        async with db.get_session() as session:
            result = await session.execute(
                select(ToolV2Model).where(ToolV2Model.tool_id == tool_id)
            )
            row = result.scalar_one_or_none()
            if row:
                schema = self._row_to_schema(row)
                self._cache[tool_id] = schema
                return schema
            return None

    async def list_all(self) -> List[ToolV2]:
        async with db.get_session() as session:
            result = await session.execute(
                select(ToolV2Model).where(ToolV2Model.status == "active")
            )
            rows = result.scalars().all()
            return [self._row_to_schema(row) for row in rows]

    async def list_by_category(self, category: str) -> List[ToolV2]:
        async with db.get_session() as session:
            result = await session.execute(
                select(ToolV2Model)
                .where(ToolV2Model.status == "active")
                .where(ToolV2Model.category == category)
            )
            rows = result.scalars().all()
            return [self._row_to_schema(row) for row in rows]

    async def delete(self, tool_id: str) -> Optional[ToolV2]:
        async with db.get_session() as session:
            result = await session.execute(
                select(ToolV2Model).where(ToolV2Model.tool_id == tool_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.status = "inactive"
                await session.commit()
                await session.refresh(row)
                if tool_id in self._cache:
                    del self._cache[tool_id]
                return self._row_to_schema(row)
            return None


tool_registry_v2 = ToolRegistryV2()
