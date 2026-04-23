from fastapi import APIRouter, status
from fastapi.responses import PlainTextResponse
from ...logs.metrics import metrics_collector
from ...memory.long_term import db
from ...memory.short_term import redis_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """Returns 503 if dependencies are not ready."""
    healthy = True
    checks = {}

    try:
        if db.engine:
            async with db.engine.connect() as conn:
                await conn.execute("SELECT 1")
            checks["database"] = "ok"
        else:
            checks["database"] = "not_initialized"
            healthy = False
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False

    try:
        if redis_client.client:
            await redis_client.client.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_initialized"
            healthy = False
    except Exception as e:
        checks["redis"] = f"error: {e}"
        healthy = False

    if not healthy:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=checks)

    return {"status": "ready", "checks": checks}


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    return {"status": "alive"}


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    return metrics_collector.get_prometheus_format()
