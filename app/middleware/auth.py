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
        public_paths = {
            "/health",
            "/docs",
            "/openapi.json",
            "/api/v1/auth/signup",
            "/api/v1/auth/login",
            "/api/v1/tasks",
        }

        if request.url.path in public_paths:
            return await call_next(request)
        
        if request.url.path.startswith("/api/v1"):
            provided_key = request.headers.get("x-api-key")
            bearer_token = request.headers.get("authorization", "").replace("Bearer ", "") if request.headers.get("authorization", "").startswith("Bearer ") else None
            
            auth_valid = False
            if provided_key:
                user = await user_repo.get_by_api_key(provided_key)
                if user and user.is_active:
                    auth_valid = True
                elif provided_key in self.api_keys:
                    auth_valid = True
            
            if bearer_token:
                payload = verify_access_token(bearer_token)
                if payload:
                    auth_valid = True
            
            if not auth_valid and not provided_key and not bearer_token:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "API key or Bearer token required"}
                )
            
            if not auth_valid:
                logger.warning(f"Invalid auth attempt from {request.client.host}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Invalid authentication"}
                )
        
        response = await call_next(request)
        return response


def get_api_keys() -> list:
    keys_str = getattr(settings, 'API_KEYS', '')
    if keys_str:
        return [k.strip() for k in keys_str.split(',') if k.strip()]
    return []
