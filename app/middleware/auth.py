from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
from jose.exceptions import ExpiredSignatureError
from ..config.settings import settings
from ..logs.logger import logger
from ..auth.utils import decode_access_token
from ..memory.long_term import db
from ..memory.models import APIKeyModel
from sqlalchemy import select
import hashlib
from datetime import datetime


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_keys: Optional[list] = None):
        super().__init__(app)
        self.api_keys = api_keys or []
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/api/v1/auth/login", "/api/v1/auth/signup"}:
            return await call_next(request)

        if request.url.path.startswith("/api/v1"):
            bearer_token = request.headers.get("authorization", "").replace("Bearer ", "") if request.headers.get("authorization", "").startswith("Bearer ") else None
            api_key = request.headers.get("x-api-key", "")

            authenticated = False

            if bearer_token:
                try:
                    payload = decode_access_token(bearer_token)
                except ExpiredSignatureError:
                    request.state.auth_error = "token_expired"
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"error": "token_expired"},
                        headers={"WWW-Authenticate": "Bearer"}
                    )
                if payload:
                    request.state.user = payload
                    request.state.auth_type = "bearer"
                    authenticated = True
                else:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"error": "invalid_token"},
                        headers={"WWW-Authenticate": "Bearer"}
                    )

            if not authenticated and api_key:
                key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                try:
                    async with db.get_session() as session:
                        result = await session.execute(select(APIKeyModel).where(APIKeyModel.key_hash == key_hash))
                        key_obj = result.scalar_one_or_none()
                        if key_obj:
                            key_obj.last_used_at = datetime.utcnow()
                            await session.commit()
                            request.state.user = {"sub": key_obj.user_id}
                            request.state.auth_type = "api_key"
                            request.state.api_key_permissions = key_obj.permissions or []
                            authenticated = True
                except Exception as e:
                    logger.warning(f"API key validation error: {e}")

            if not authenticated:
                logger.warning(f"Invalid auth attempt from {getattr(request.client, 'host', 'unknown') if request.client else 'unknown'}")
                return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Unauthorized"})

        response = await call_next(request)
        return response


def get_api_keys() -> list:
    keys_str = getattr(settings, 'API_KEYS', '')
    if keys_str:
        return [k.strip() for k in keys_str.split(',') if k.strip()]
    return []
