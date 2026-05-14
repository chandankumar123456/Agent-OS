import os
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import time
from ..config.settings import settings
from ..logs.logger import logger
from ..memory.short_term import redis_client

# Rate limits per minute
DEFAULT_LIMIT = 60
FREE_USER_LIMIT = 60
PREMIUM_USER_LIMIT = 300
API_KEY_LIMIT = 120
BURST_SIZE = 10

# Local development: much higher limits to avoid blocking during testing
LOCAL_DEV_LIMIT = 600
LOCAL_DEV_BURST = 100


def _is_local_dev() -> bool:
    """Return True if running in local development mode."""
    return os.environ.get("AGENTOS_ENV", "").lower() == "development" or os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = DEFAULT_LIMIT,
        burst_size: int = BURST_SIZE
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size

    async def _get_client_info(self, request: Request) -> tuple[str, int]:
        """Returns (client_id, limit)"""
        # Check API key first
        api_key = request.headers.get("x-api-key", "")
        if api_key:
            return f"ratelimit:apikey:{api_key}", API_KEY_LIMIT

        # Check bearer token for user info
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            from ..auth.utils import verify_access_token
            payload = verify_access_token(auth_header.removeprefix("Bearer ").strip())
            if payload and payload.get("sub"):
                user_id = str(payload["sub"])
                role = payload.get("role", "user")
                if role == "admin":
                    return f"ratelimit:user:{user_id}", PREMIUM_USER_LIMIT
                return f"ratelimit:user:{user_id}", FREE_USER_LIMIT

        # Fallback to IP
        ip = request.client.host if request.client else "unknown"
        return f"ratelimit:ip:{ip}", self.requests_per_minute

    async def _is_rate_limited(self, client_id: str, limit: int) -> tuple[bool, int, int]:
        if not redis_client.client:
            return False, 0, limit

        current_time = int(time.time())
        window = current_time // 60
        key = f"agentos:{client_id}:{window}"

        try:
            pipe = redis_client.client.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            results = await pipe.execute()
            count = results[0]

            remaining = max(0, limit - count)

            if count > limit:
                retry_after = 60 - (current_time % 60)
                return True, retry_after, remaining

            # Burst check: count requests in the last 1 second
            burst_key = f"agentos:{client_id}:burst:{current_time}"
            burst_pipe = redis_client.client.pipeline()
            burst_pipe.incr(burst_key)
            burst_pipe.expire(burst_key, 1)
            burst_results = await burst_pipe.execute()
            burst_count = burst_results[0]

            burst_limit = LOCAL_DEV_BURST if _is_local_dev() else self.burst_size
            if burst_count > burst_limit:
                retry_after = 1
                return True, retry_after, remaining

            return False, 0, remaining
        except Exception as e:
            logger.error(f"Redis rate limit check failed, rejecting request: {e}")
            # Fail closed: reject request when rate limit system is unavailable
            return True, 60, 0  # is_limited=True, retry_after=60, remaining=0

    async def dispatch(self, request: Request, call_next):
        # In desktop mode, skip rate limiting for local IPC
        if _is_desktop_mode():
            return await call_next(request)

        if request.url.path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        client_id, limit = await self._get_client_info(request)

        # Local development: use relaxed limits
        if _is_local_dev():
            limit = LOCAL_DEV_LIMIT

        is_limited, retry_after, remaining = await self._is_rate_limited(client_id, limit)

        if is_limited:
            logger.warning(f"Rate limit exceeded for {client_id}")
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Rate limit exceeded",
                        "context": {"retry_after": retry_after}
                    }
                }
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def get_rate_limit() -> int:
    return getattr(settings, 'RATE_LIMIT_PER_MINUTE', DEFAULT_LIMIT)
