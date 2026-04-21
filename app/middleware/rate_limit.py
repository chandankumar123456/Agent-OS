from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict
import time
from collections import defaultdict
from ..config.settings import settings
from ..logs.logger import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_size: int = 10
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.client_requests: Dict[str, list] = defaultdict(list)
    
    def _clean_old_requests(self, client_id: str, current_time: float):
        minute_ago = current_time - 60
        self.client_requests[client_id] = [
            t for t in self.client_requests[client_id] if t > minute_ago
        ]
    
    def _is_rate_limited(self, client_id: str) -> bool:
        current_time = time.time()
        self._clean_old_requests(client_id, current_time)
        
        if len(self.client_requests[client_id]) >= self.requests_per_minute:
            return True
        
        recent_requests = [
            t for t in self.client_requests[client_id]
            if t > current_time - 1
        ]
        
        if len(recent_requests) >= self.burst_size:
            return True
        
        self.client_requests[client_id].append(current_time)
        return False
    
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        client_id = request.client.host if request.client else "unknown"
        
        if self._is_rate_limited(client_id):
            logger.warning(f"Rate limit exceeded for {client_id}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": 60
                }
            )
        
        response = await call_next(request)
        return response


def get_rate_limit() -> int:
    return getattr(settings, 'RATE_LIMIT_PER_MINUTE', 60)