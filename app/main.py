from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .config.settings import settings
from .api import api_router
from .api.routes.health import router as health_router

from .logs.logger import logger

# gRPC mode support
from .proto.grpc_client import GRPCClient, GRPCClientConfig
from .memory.long_term import db
from .memory.short_term import redis_client
from .migrations.runner import run_pending_migrations
from .middleware.auth import APIKeyMiddleware, get_api_keys
from .middleware.rate_limit import RateLimitMiddleware, get_rate_limit
from .middleware.request_logging import RequestLoggingMiddleware
from .runtime.runtime import AgentRuntime
from .logs.metrics import metrics_collector
from .mcp.monitor import mcp_health_monitor
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from .orchestrator.errors import AgentOSError, ErrorCode


async def _check_dependencies() -> None:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required but not set")
    # Skip Redis check in gRPC mode (supervisor handles Redis)
    if settings.RUNTIME_MODE.lower() != "grpc" and not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL is required but not set")
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required but not set")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    sys.stdout.write("[LIFESPAN] Agent-OS starting up\n")
    sys.stdout.flush()
    logger.info("Agent-OS starting up")

    await _check_dependencies()

    initialized = []

    try:
        await db.connect()
        logger.info("Database connected successfully")
        initialized.append("db")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise RuntimeError(f"Database connection failed: {e}") from e

    try:
        await run_pending_migrations()
        logger.info("Database migrations applied")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise RuntimeError(f"Migration failed: {e}") from e

    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
        initialized.append("redis")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise RuntimeError(f"Redis connection failed: {e}") from e

    try:
        from .memory.redis_pubsub import redis_pubsub_client
        await redis_pubsub_client.connect()
        logger.info("Redis PubSub client connected")
        initialized.append("redis_pubsub")
    except Exception as e:
        logger.error(f"Redis PubSub client connection failed: {e}")

    try:
        runtime = AgentRuntime()
        await runtime.initialize()
        app.state.runtime = runtime
        
        # Log runtime mode for debugging
        if hasattr(runtime, 'is_grpc_mode') and runtime.is_grpc_mode():
            logger.info("AgentRuntime initialized in gRPC mode")
        else:
            logger.info("AgentRuntime initialized in HTTP mode")
        
        initialized.append("runtime")
    except Exception as e:
        logger.error(f"AgentRuntime initialization failed: {e}")
        raise RuntimeError(f"AgentRuntime initialization failed: {e}") from e

    try:
        mcp_health_monitor.start()
        logger.info("MCP health monitor started")
        initialized.append("mcp_monitor")
    except Exception as e:
        logger.error(f"MCP health monitor start failed: {e}")

    try:
        from .tools.builtin import register_builtin_tools
        from .tools.registry import tool_registry
        register_builtin_tools(tool_registry)
        logger.info("Built-in tools registered")
        initialized.append("builtin_tools")
    except Exception as e:
        logger.error(f"Built-in tools registration failed: {e}")

    try:
        from .mcp.client_manager import mcp_client_manager
        await mcp_client_manager.start_system_servers()
        logger.info("MCP system servers started")
        initialized.append("mcp_servers")
    except BaseException as e:
        logger.error(f"MCP system servers start failed: {e}")

    try:
        from .tools.registry import tool_registry
        await tool_registry.discover_mcp_tools()
        logger.info("MCP tools discovered at startup")
        initialized.append("mcp_tools_discovered")
    except Exception as e:
        logger.error(f"MCP tool discovery failed at startup: {e}")

    # Initialize gRPC client if in grpc mode
    if settings.RUNTIME_MODE.lower() == "grpc":
        try:
            grpc_config = GRPCClientConfig(
                host=settings.GRPC_HOST,
                port=settings.GRPC_PORT,
                connection_timeout=settings.GRPC_CONNECTION_TIMEOUT,
                keepalive_timeout=settings.GRPC_KEEPALIVE_TIMEOUT,
                max_send_message_length=settings.GRPC_MAX_MESSAGE_LENGTH_MB * 1024 * 1024,
                max_receive_message_length=settings.GRPC_MAX_MESSAGE_LENGTH_MB * 1024 * 1024,
            )
            grpc_client = GRPCClient(config=grpc_config)
            await grpc_client.connect()
            app.state.grpc_client = grpc_client
            initialized.append("grpc_client")
            logger.info(f"gRPC client initialized in {settings.RUNTIME_MODE} mode")
        except Exception as e:
            logger.error(f"gRPC client initialization failed: {e}")
            raise RuntimeError(f"gRPC client initialization failed: {e}") from e
    else:
        logger.info(f"Running in HTTP mode (RUNTIME_MODE={settings.RUNTIME_MODE})")

    yield

    if "mcp_servers" in initialized:
        try:
            from .mcp.client_manager import mcp_client_manager
            await mcp_client_manager.disconnect_all()
            logger.info("MCP system servers stopped")
        except Exception as e:
            logger.error(f"MCP system servers stop failed: {e}")

    try:
        from .environments.desktop_env import DesktopSessionManager
        await DesktopSessionManager().close_all()
        logger.info("Desktop sessions closed")
    except Exception as e:
        logger.error(f"Desktop session close_all failed: {e}")

    if "mcp_monitor" in initialized:
        try:
            mcp_health_monitor.stop()
        except Exception as e:
            logger.error(f"MCP health monitor stop failed: {e}")

    if "runtime" in initialized:
        try:
            await app.state.runtime.shutdown_all()
        except Exception as e:
            logger.error(f"AgentRuntime shutdown failed: {e}")

    if "grpc_client" in initialized:
        try:
            await app.state.grpc_client.close()
            logger.info("gRPC client closed")
        except Exception as e:
            logger.error(f"gRPC client close failed: {e}")

    if "db" in initialized:
        try:
            await db.disconnect()
        except Exception as e:
            logger.error(f"Database disconnect failed: {e}")

    if "redis" in initialized:
        try:
            await redis_client.disconnect()
        except Exception as e:
            logger.error(f"Redis disconnect failed: {e}")

    if "redis_pubsub" in initialized:
        try:
            from .memory.redis_pubsub import redis_pubsub_client
            await redis_pubsub_client.disconnect()
        except Exception as e:
            logger.error(f"Redis PubSub disconnect failed: {e}")

    logger.info("Agent-OS shutting down")


from .middleware.validation import InputValidationMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="MCP-Based Multi-Agent Operating System",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan
)

# CORS: avoid wildcard + credentials combination (browser security anti-pattern)
_cors_origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"]
_allow_credentials = False if _cors_origins == ["*"] else True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(InputValidationMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=get_rate_limit())

api_keys = get_api_keys()
if api_keys:
    app.add_middleware(APIKeyMiddleware, api_keys=api_keys)

app.include_router(api_router, prefix="/api/v1")
app.include_router(health_router)
from .api.ws import websocket_endpoint
app.add_api_websocket_route("/ws/tasks/{task_id}", websocket_endpoint)

from .logs.metrics import metrics_collector

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
                "context": exc.context
            }
        }
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
        content={
            "error": {
                "code": code,
                "message": detail,
                "context": {}
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Validation error",
                "context": {"details": exc.errors()}
            }
        }
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
                "context": {}
            }
        }
    )


@app.middleware("http")
async def metrics_middleware(request, call_next):
    import time
    start_time = time.time()

    exc_to_reraise = None
    try:
        response = await call_next(request)
        status = str(response.status_code)
    except Exception as exc:
        status = "500"
        response = None
        exc_to_reraise = exc

    process_time = time.time() - start_time
    path = request.url.path
    method = request.method

    metrics_collector.inc_counter("http_requests_total", {"method": method, "path": path, "status": status})
    metrics_collector.observe_histogram("http_request_duration_seconds", process_time, {"method": method, "path": path})

    if int(status) >= 400:
        metrics_collector.inc_counter("http_errors_total", {"method": method, "path": path, "status": status})

    if exc_to_reraise is not None:
        raise exc_to_reraise
    return response


@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.VERSION}
