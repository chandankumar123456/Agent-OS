from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
from ..config.settings import settings
from ..logs.logger import logger
from ..auth.utils import verify_access_token
from ..memory.long_term import user_repo
import time


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_keys: Optional[list] = None):
        super().__init__(app)
        self.api_keys = api_keys or []
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/api/v1/auth/login", "/api/v1/auth/signup"}:
            return await call_next(request)

        if request.url.path.startswith("/api/v1") or request.url.path in {"/health", "/metrics"}:
            bearer_token = request.headers.get("authorization", "").replace("Bearer ", "") if request.headers.get("authorization", "").startswith("Bearer ") else None

            if not bearer_token:
                return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Unauthorized"})

            payload = verify_access_token(bearer_token)
            if not payload:
                logger.warning(f"Invalid auth attempt from {request.client.host}")
                return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "Unauthorized"})

        response = await call_next(request)
        return response


def get_api_keys() -> list:
    keys_str = getattr(settings, 'API_KEYS', '')
    if keys_str:
        return [k.strip() for k in keys_str.split(',') if k.strip()]
    return []
