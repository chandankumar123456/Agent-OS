import os
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

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
    return (
        os.environ.get("AGENTOS_ENV", "").lower() == "development"
        or os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    )


def _is_desktop_mode() -> bool:
    """Check if running in desktop-native gRPC mode."""
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


async def classify_client(
    *,
    api_key_header: str,
    authorization_header: str,
    client_host: Optional[str],
    default_limit: int,
) -> tuple[str, int]:
    """Pure-ish classification of a request into ``(client_id, limit)``.

    Looks at the API key header first, then the bearer token (decoded
    locally, no I/O), then falls back to the client IP.  Imports
    ``verify_access_token`` lazily to avoid heavy import cycles.
    """
    if api_key_header:
        return f"ratelimit:apikey:{api_key_header}", API_KEY_LIMIT

    if authorization_header.startswith("Bearer "):
        from ..auth.utils import verify_access_token

        payload = verify_access_token(
            authorization_header.removeprefix("Bearer ").strip()
        )
        if payload and payload.get("sub"):
            user_id = str(payload["sub"])
            role = payload.get("role", "user")
            if role == "admin":
                return f"ratelimit:user:{user_id}", PREMIUM_USER_LIMIT
            return f"ratelimit:user:{user_id}", FREE_USER_LIMIT

    return f"ratelimit:ip:{client_host or 'unknown'}", default_limit


async def check_rate_limit(
    client_id: str, limit: int, burst_size: int
) -> tuple[bool, int, int]:
    """Pure rate-limit check against Redis.

    Returns ``(is_limited, retry_after_seconds, remaining)``.  Fails
    closed (returns ``is_limited=True``) when Redis is unreachable.
    """
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

        burst_limit = LOCAL_DEV_BURST if _is_local_dev() else burst_size
        if burst_count > burst_limit:
            return True, 1, remaining

        return False, 0, remaining
    except Exception as e:
        logger.error(f"Redis rate limit check failed, rejecting request: {e}")
        # Fail closed: reject when the rate-limit system is unavailable.
        return True, 60, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_minute: int = DEFAULT_LIMIT,
        burst_size: int = BURST_SIZE,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size

    async def _get_client_info(self, request: Request) -> tuple[str, int]:
        """Returns (client_id, limit). Thin wrapper over classify_client."""
        return await classify_client(
            api_key_header=request.headers.get("x-api-key", ""),
            authorization_header=request.headers.get("authorization", ""),
            client_host=request.client.host if request.client else None,
            default_limit=self.requests_per_minute,
        )

    async def _is_rate_limited(self, client_id: str, limit: int) -> tuple[bool, int, int]:
        """Thin wrapper kept for backward compatibility (tests patch this)."""
        return await check_rate_limit(client_id, limit, self.burst_size)

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
                        "context": {"retry_after": retry_after},
                    }
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


def get_rate_limit() -> int:
    return getattr(settings, "RATE_LIMIT_PER_MINUTE", DEFAULT_LIMIT)
