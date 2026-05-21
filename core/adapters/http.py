"""Optional FastAPI HTTP adapter for the AgentOS kernel.

This module wraps the unified AgentKernel with a FastAPI application so
that clients who need a REST/WebSocket interface can opt into it.

Install the extra to use this module::

    pip install agentos[http]

The adapter does NOT create its own kernel; it receives a running kernel
instance and translates HTTP requests into kernel calls.
"""

from __future__ import annotations

try:
    import fastapi  # noqa: F401
except ImportError as _exc:
    raise ImportError(
        "The HTTP adapter requires FastAPI and its dependencies. "
        "Install them with:  pip install agentos[http]"
    ) from _exc

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from core.desktop_native.kernel import AgentKernel


def build_http_app(*, kernel: "AgentKernel") -> FastAPI:
    """Construct a FastAPI application backed by the given kernel.

    The app includes all API routes, middleware, and error handlers from
    the existing ``core.api`` and ``core.middleware`` packages.

    Args:
        kernel: A running AgentKernel instance.

    Returns:
        A fully-configured FastAPI application ready to be served by uvicorn.
    """
    from contextlib import asynccontextmanager

    from ..config.settings import settings
    from ..api import api_router
    from ..api.routes.health import router as health_router
    from ..logs.logger import logger
    from ..middleware.auth import APIKeyMiddleware, get_api_keys
    from ..middleware.rate_limit import RateLimitMiddleware, get_rate_limit
    from ..middleware.request_logging import RequestLoggingMiddleware
    from ..middleware.validation import InputValidationMiddleware
    from ..middleware.csrf import CSRFMiddleware
    from ..orchestrator.errors import AgentOSError, ErrorCode
    from ..logs.metrics import metrics_collector

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Kernel is already running; nothing to boot.
        logger.info("HTTP adapter attached to running AgentKernel")
        app.state.kernel = kernel
        yield
        logger.info("HTTP adapter detached")

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description="AgentOS HTTP Adapter",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # CORS
    cors_origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"]
    allow_creds = cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(InputValidationMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=get_rate_limit())

    api_keys = get_api_keys()
    if api_keys:
        app.add_middleware(APIKeyMiddleware, api_keys=api_keys)

    app.add_middleware(CSRFMiddleware)

    # Routes
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(health_router)

    # WebSocket
    from ..api.ws import websocket_endpoint
    app.add_api_websocket_route("/ws/tasks/{task_id}", websocket_endpoint)

    # Error handlers
    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse, PlainTextResponse
    from fastapi.exceptions import RequestValidationError

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics():
        return metrics_collector.get_prometheus_format()

    @app.exception_handler(AgentOSError)
    async def agent_error_handler(_: Request, exc: AgentOSError):
        logger.log_error(exc)
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.code.value if hasattr(exc.code, "value") else str(exc.code),
                    "message": exc.message,
                    "context": exc.context,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        logger.log_error(exc)
        code_map = {
            401: ErrorCode.AUTH_UNAUTHORIZED.value,
            403: ErrorCode.AUTH_FORBIDDEN.value,
            404: ErrorCode.TASK_NOT_FOUND.value,
            422: ErrorCode.VALIDATION_ERROR.value,
            429: ErrorCode.RATE_LIMIT_EXCEEDED.value,
            503: ErrorCode.TASK_QUEUE_UNAVAILABLE.value,
        }
        code = code_map.get(exc.status_code, ErrorCode.UNKNOWN_ERROR.value)
        detail = exc.detail if isinstance(exc.detail, str) else "Error"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": detail, "context": {}}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": "Validation error",
                    "context": {"details": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "Internal server error",
                    "context": {},
                }
            },
        )

    return app


__all__ = ["build_http_app"]
