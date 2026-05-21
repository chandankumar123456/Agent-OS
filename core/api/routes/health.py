from fastapi import APIRouter, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from ...logs.metrics import metrics_collector
from ...memory.long_term import db
from ...memory.short_term import redis_client
from ...config.settings import settings
from ...config.mode import get_runtime_mode

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "mode": get_runtime_mode().value,
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """Returns 503 if dependencies are not ready."""
    healthy = True
    checks = {}

    try:
        if db.engine:
            async with db.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
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
            # Redis is optional when REDIS_URL is not set
            if settings.REDIS_URL:
                checks["redis"] = "not_initialized"
                healthy = False
            else:
                checks["redis"] = "skipped (no REDIS_URL)"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        if settings.REDIS_URL:
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


@router.post("/maintenance/purge")
async def trigger_purge(retention_days: int = 30):
    """Trigger data purging for records older than retention_days."""
    from ...maintenance import purge_old_data
    result = await purge_old_data(retention_days)
    return {"purged": result}
