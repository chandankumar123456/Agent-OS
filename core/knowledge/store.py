from typing import List, Optional
import uuid

from sqlalchemy import select, delete

from ..memory.models import KnowledgeSourceModel, KnowledgeChunkModel
from ..memory.long_term import db


async def create_source(
    user_id: str, name: str, type: str, content_preview: str
) -> KnowledgeSourceModel:
    async with db.get_session() as session:
        source = KnowledgeSourceModel(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            type=type,
            content_preview=content_preview[:1000],
            chunk_count=0,
            status="active",
        )
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source


async def add_chunks(source_id: str, chunks: List[str]) -> int:
    async with db.get_session() as session:
        count = 0
        for i, content in enumerate(chunks):
            chunk = KnowledgeChunkModel(
                id=str(uuid.uuid4()),
                source_id=source_id,
                content=content,
                chunk_metadata={"index": i},
            )
            session.add(chunk)
            count += 1
        result = await session.execute(
            select(KnowledgeSourceModel).where(KnowledgeSourceModel.id == source_id)
        )
        source = result.scalar_one_or_none()
        if source:
            source.chunk_count = count
        await session.commit()
        return count


async def list_sources(user_id: str) -> List[KnowledgeSourceModel]:
    async with db.get_session() as session:
        result = await session.execute(
            select(KnowledgeSourceModel)
            .where(KnowledgeSourceModel.user_id == user_id)
            .order_by(KnowledgeSourceModel.created_at.desc())
        )
        return result.scalars().all()


async def get_source(source_id: str) -> Optional[KnowledgeSourceModel]:
    async with db.get_session() as session:
        result = await session.execute(
            select(KnowledgeSourceModel).where(KnowledgeSourceModel.id == source_id)
        )
        return result.scalar_one_or_none()


async def delete_source(source_id: str) -> bool:
    async with db.get_session() as session:
        result = await session.execute(
            select(KnowledgeSourceModel).where(KnowledgeSourceModel.id == source_id)
        )
        source = result.scalar_one_or_none()
        if not source:
            return False
        await session.execute(
            delete(KnowledgeChunkModel).where(KnowledgeChunkModel.source_id == source_id)
        )
        await session.delete(source)
        await session.commit()
        return True


async def get_chunks(source_id: str) -> List[KnowledgeChunkModel]:
    async with db.get_session() as session:
        result = await session.execute(
            select(KnowledgeChunkModel)
            .where(KnowledgeChunkModel.source_id == source_id)
            .order_by(KnowledgeChunkModel.created_at)
        )
        return result.scalars().all()


async def search_chunks(
    query: str, source_ids: List[str], top_k: int = 5
) -> List[KnowledgeChunkModel]:
    async with db.get_session() as session:
        from sqlalchemy import or_

        words = [w for w in query.split() if len(w) > 2]
        if words:
            conditions = [KnowledgeChunkModel.content.ilike(f"%{w}%") for w in words]
        else:
            conditions = [KnowledgeChunkModel.content.ilike(f"%{query}%")]
        stmt = (
            select(KnowledgeChunkModel)
            .where(KnowledgeChunkModel.source_id.in_(source_ids))
            .where(or_(*conditions))
            .limit(top_k)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
