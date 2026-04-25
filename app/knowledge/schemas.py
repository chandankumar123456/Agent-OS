from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class KnowledgeSource(BaseModel):
    id: str
    name: str
    type: str
    content_preview: Optional[str] = None
    chunk_count: int = 0
    status: str
    created_at: datetime


class Chunk(BaseModel):
    id: str
    source_id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeQueryRequest(BaseModel):
    query: str
    top_k: int = 5


class KnowledgeQueryResponse(BaseModel):
    chunks: List[Chunk]
