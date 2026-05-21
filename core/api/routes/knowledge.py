from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import List

from ...knowledge.parser import parse_document, split_text_into_chunks
from ...knowledge.store import create_source, add_chunks, list_sources, get_source, delete_source
from ...knowledge.rag import retrieve_relevant_chunks
from ...knowledge.schemas import KnowledgeSource, KnowledgeQueryRequest, KnowledgeQueryResponse
from ...api.deps import get_current_user

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/upload", response_model=KnowledgeSource)
async def upload_document(
    file: UploadFile = File(...),
    current_user: object = Depends(get_current_user),
):
    user_id = str(getattr(current_user, "id", "system"))
    content = await file.read()
    text = parse_document(content, file.filename or "unknown")
    chunks = split_text_into_chunks(text, chunk_size=500, overlap=50)
    source = await create_source(
        user_id=user_id,
        name=file.filename or "unknown",
        type="document",
        content_preview=text[:500],
    )
    await add_chunks(source.id, chunks)
    return KnowledgeSource(
        id=source.id,
        name=source.name,
        type=source.type,
        content_preview=source.content_preview,
        chunk_count=len(chunks),
        status=source.status,
        created_at=source.created_at,
    )


@router.get("", response_model=List[KnowledgeSource])
async def get_knowledge_sources(current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    sources = await list_sources(user_id)
    return [
        KnowledgeSource(
            id=s.id,
            name=s.name,
            type=s.type,
            content_preview=s.content_preview,
            chunk_count=s.chunk_count,
            status=s.status,
            created_at=s.created_at,
        )
        for s in sources
    ]


@router.get("/{source_id}", response_model=KnowledgeSource)
async def get_knowledge_source(source_id: str, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return KnowledgeSource(
        id=source.id,
        name=source.name,
        type=source.type,
        content_preview=source.content_preview,
        chunk_count=source.chunk_count,
        status=source.status,
        created_at=source.created_at,
    )


@router.delete("/{source_id}")
async def delete_knowledge_source(source_id: str, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    success = await delete_source(source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"success": True}


@router.post("/{source_id}/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(source_id: str, request: KnowledgeQueryRequest, current_user: object = Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    source = await get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    chunks = await retrieve_relevant_chunks(request.query, [source_id], request.top_k)
    return KnowledgeQueryResponse(chunks=chunks)
