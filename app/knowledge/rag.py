from typing import List
from .store import search_chunks
from .schemas import Chunk


async def retrieve_relevant_chunks(
    query: str, source_ids: List[str], top_k: int = 5
) -> List[Chunk]:
    rows = await search_chunks(query, source_ids, top_k)
    return [
        Chunk(
            id=row.id,
            source_id=row.source_id,
            content=row.content,
            metadata=row.chunk_metadata,
        )
        for row in rows
    ]
