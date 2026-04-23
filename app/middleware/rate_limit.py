from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import time
from ..config.settings import settings
from ..logs.logger import logger
from ..memory.short_term import redis_client


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

    async def _get_user_id(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            from ..auth.utils import verify_access_token
            payload = verify_access_token(auth_header.removeprefix("Bearer ").strip())
            if payload and payload.get("sub"):
                return str(payload["sub"])
        return request.client.host if request.client else "unknown"

    async def _is_rate_limited(self, client_id: str) -> bool:
        current_time = time.time()
        key = f"agentos:ratelimit:{client_id}"

        try:
            if redis_client.client:
                pipe = redis_client.client.pipeline()
                pipe.zremrangebyscore(key, 0, current_time - 60)
                pipe.zadd(key, {str(current_time): current_time})
                pipe.zcard(key)
                pipe.expire(key, 60)
                results = await pipe.execute()
                request_count = results[2]

                if request_count > self.requests_per_minute:
                    return True

                recent_count = await redis_client.client.zcount(
                    key, current_time - 1, current_time
                )
                if recent_count > self.burst_size:
                    return True

                return False
        except Exception as e:
            logger.warning(f"Redis rate limit check failed, allowing request: {e}")
            return False

        return False

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        client_id = await self._get_user_id(request)

        if await self._is_rate_limited(client_id):
            logger.warning(f"Rate limit exceeded for {client_id}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Rate limit exceeded",
                        "context": {"retry_after": 60}
                    }
                }
            )

        response = await call_next(request)
        return response


def get_rate_limit() -> int:
    return getattr(settings, 'RATE_LIMIT_PER_MINUTE', 60)
