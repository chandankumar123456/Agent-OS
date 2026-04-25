from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4
from datetime import datetime

from ...memory.long_term import db
from ...memory.models import ChatSessionModel, ChatMessageModel
from ...api.deps import get_current_user
from ...logs.logger import logger
from sqlalchemy import select, desc

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    agent_id: Optional[str] = None
    title: Optional[str] = "New Chat"


class CreateSessionResponse(BaseModel):
    id: str
    user_id: str
    agent_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SendMessageRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime


class SessionResponse(BaseModel):
    id: str
    user_id: str
    agent_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    req: CreateSessionRequest,
    current_user=Depends(get_current_user),
):
    user_id = str(getattr(current_user, "id", "system"))
    session_id = str(uuid4())
    async with db.get_session() as session:
        chat_session = ChatSessionModel(
            id=session_id,
            user_id=user_id,
            agent_id=req.agent_id,
            title=req.title or "New Chat",
        )
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)
        logger.info(f"User {user_id} created chat session {session_id}")
        return CreateSessionResponse(
            id=chat_session.id,
            user_id=chat_session.user_id,
            agent_id=chat_session.agent_id,
            title=chat_session.title,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
        )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(current_user=Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    async with db.get_session() as session:
        result = await session.execute(
            select(ChatSessionModel)
            .where(ChatSessionModel.user_id == user_id)
            .order_by(desc(ChatSessionModel.updated_at))
        )
        rows = result.scalars().all()
        return [
            SessionResponse(
                id=r.id,
                user_id=r.user_id,
                agent_id=r.agent_id,
                title=r.title,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_message(
    session_id: str,
    req: SendMessageRequest,
    current_user=Depends(get_current_user),
):
    user_id = str(getattr(current_user, "id", "system"))
    async with db.get_session() as session:
        result = await session.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Store user message
        user_msg = ChatMessageModel(
            id=str(uuid4()),
            session_id=session_id,
            role="user",
            content=req.content,
        )
        session.add(user_msg)

        # Update session timestamp
        chat_session.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(user_msg)

        return MessageResponse(
            id=user_msg.id,
            session_id=user_msg.session_id,
            role=user_msg.role,
            content=user_msg.content,
            created_at=user_msg.created_at,
        )


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_messages(session_id: str, current_user=Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    async with db.get_session() as session:
        result = await session.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        result = await session.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        rows = result.scalars().all()
        return [
            MessageResponse(
                id=r.id,
                session_id=r.session_id,
                role=r.role,
                content=r.content,
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user=Depends(get_current_user)):
    user_id = str(getattr(current_user, "id", "system"))
    async with db.get_session() as session:
        result = await session.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.id == session_id,
                ChatSessionModel.user_id == user_id,
            )
        )
        chat_session = result.scalar_one_or_none()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Delete associated messages
        await session.execute(
            ChatMessageModel.__table__.delete().where(
                ChatMessageModel.session_id == session_id
            )
        )
        await session.delete(chat_session)
        await session.commit()
        logger.info(f"User {user_id} deleted chat session {session_id}")
        return {"message": f"Session {session_id} deleted"}
