import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..logs.logger import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs incoming HTTP requests and their responses."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        path = request.url.path
        method = request.method
        client_ip = request.client.host if request.client else "unknown"

        # Skip logging for health checks to reduce noise
        if path in ("/health", "/health/ready", "/health/live", "/health/metrics"):
            return await call_next(request)

        logger.info(f"[REQUEST] {method} {path} from {client_ip}")

        try:
            response = await call_next(request)
            duration = (time.time() - start_time) * 1000
            status_code = response.status_code
            logger.info(
                f"[RESPONSE] {method} {path} - {status_code} in {duration:.2f}ms"
            )
            return response
        except Exception as exc:
            duration = (time.time() - start_time) * 1000
            logger.error(
                f"[RESPONSE] {method} {path} - ERROR ({type(exc).__name__}) in {duration:.2f}ms"
            )
            raise
