from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from uuid import uuid4
import hashlib
from ...auth.utils import generate_api_key
from ...api.deps import get_current_user
from ...memory.long_term import db
from ...memory.models import APIKeyModel
from ...logs.logger import logger
from sqlalchemy import select

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class APIKeyCreate(BaseModel):
    name: str
    permissions: List[str] = []


class APIKeyResponse(BaseModel):
    id: str
    name: str
    permissions: List[str]
    last_used_at: str | None
    created_at: str


class APIKeyCreateResponse(BaseModel):
    id: str
    name: str
    key: str
    permissions: List[str]
    created_at: str


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@router.post("", response_model=APIKeyCreateResponse)
async def create_api_key(
    request: APIKeyCreate,
    current_user = Depends(get_current_user)
):
    raw_key = generate_api_key()
    key_hash = _hash_key(raw_key)

    api_key = APIKeyModel(
        id=str(uuid4()),
        user_id=str(current_user.id),
        key_hash=key_hash,
        name=request.name,
        permissions=request.permissions,
    )
    async with db.get_session() as session:
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

    logger.info(f"API key created: {api_key.id} for user {current_user.id}")
    return APIKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        permissions=api_key.permissions or [],
        created_at=api_key.created_at.isoformat() if api_key.created_at else ""
    )


@router.get("", response_model=List[APIKeyResponse])
async def list_api_keys(current_user = Depends(get_current_user)):
    async with db.get_session() as session:
        result = await session.execute(
            select(APIKeyModel).where(APIKeyModel.user_id == str(current_user.id))
        )
        keys = result.scalars().all()

        return [
            APIKeyResponse(
                id=k.id,
                name=k.name,
                permissions=k.permissions or [],
                last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
                created_at=k.created_at.isoformat() if k.created_at else ""
            )
            for k in keys
        ]


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, current_user = Depends(get_current_user)):
    async with db.get_session() as session:
        result = await session.execute(
            select(APIKeyModel)
            .where(APIKeyModel.id == key_id)
            .where(APIKeyModel.user_id == str(current_user.id))
        )
        key = result.scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        await session.delete(key)
        await session.commit()

    logger.info(f"API key revoked: {key_id} by user {current_user.id}")
    return {"success": True}
