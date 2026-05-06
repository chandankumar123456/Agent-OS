from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from ...api.deps import get_current_user
from ...logs.metrics import metrics_collector
from ...logs.anomaly import anomaly_detector
from ...logs.alerts import alert_manager
from ...logs.profiler import performance_profiler
from ...runtime.resource_limits import resource_limit_enforcer
from ...runtime.scaling import scaling_coordinator
from ...logs.tracing import trace_manager
from ...memory.long_term import trace_repo

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics")
async def get_metrics_summary(current_user=Depends(get_current_user)):
    """Return aggregated system metrics as JSON."""
    return metrics_collector.get_json_summary()


@router.get("/metrics/prometheus")
async def get_prometheus_metrics(current_user=Depends(get_current_user)):
    """Return metrics in Prometheus text format."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=metrics_collector.get_prometheus_format())


@router.get("/traces/{task_id}")
async def get_task_traces(task_id: str, current_user=Depends(get_current_user)):
    """Return trace spans for a given task."""
    try:
        spans = trace_manager.get_trace(task_id)
        if not spans:
            db_spans = await trace_manager.get_trace_db(task_id)
            spans = db_spans
        return {
            "task_id": task_id,
            "spans": [
                {
                    "span_id": s.span_id,
                    "operation": s.operation,
                    "agent_name": s.agent_name,
                    "status": s.status,
                    "start_time": s.start_time.isoformat() if s.start_time else None,
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "error": s.error,
                    "metadata": s.metadata,
                }
                for s in spans
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/costs")
async def get_cost_breakdown(
    scope: str = "system",
    period: str = "24h",
    current_user=Depends(get_current_user)
):
    """Return cost breakdown: per-task, per-agent, per-tool, per-user, time-series."""
    tokens_total = sum(metrics_collector._counters.get("tokens_total", {}).values())
    desktop_tasks = sum(metrics_collector._counters.get("desktop_task_total", {}).values())

    return {
        "scope": scope,
        "period": period,
        "tokens_total": tokens_total,
        "desktop_tasks": desktop_tasks,
        "estimated_cost_usd": round(tokens_total * 0.00001, 4),
        "breakdown": {
            "tokens": dict(metrics_collector._counters.get("tokens_total", {})),
            "desktop": dict(metrics_collector._counters.get("desktop_task_total", {})),
        }
    }


@router.get("/anomalies")
async def get_anomalies(current_user=Depends(get_current_user)):
    """Return current anomaly report."""
    report = anomaly_detector.analyze()
    return {
        "severity": report.severity.value,
        "anomalies": [
            {
                "metric": a.metric,
                "severity": a.severity.value,
                "observed_value": a.observed_value,
                "expected_range": a.expected_range,
                "message": a.message,
                "timestamp": a.timestamp,
            }
            for a in report.anomalies
        ],
        "recommendations": report.recommendations,
    }


@router.get("/alerts")
async def get_alert_history(
    limit: int = 100,
    current_user=Depends(get_current_user)
):
    """Return recent alert history."""
    history = alert_manager.get_alert_history(limit)
    return {
        "alerts": [
            {
                "severity": a.severity.value,
                "message": a.message,
                "triggered_rule": a.triggered_rule,
                "timestamp": a.timestamp,
                "context": a.context,
            }
            for a in history
        ]
    }


@router.post("/alerts/evaluate")
async def evaluate_alert_rules(current_user=Depends(get_current_user)):
    """Manually trigger alert rule evaluation."""
    triggered = alert_manager.evaluate()
    return {
        "triggered_count": len(triggered),
        "alerts": [
            {
                "severity": a.severity.value,
                "message": a.message,
                "triggered_rule": a.triggered_rule,
                "timestamp": a.timestamp,
            }
            for a in triggered
        ]
    }


@router.get("/profile/{task_id}")
async def get_task_profile(task_id: str, current_user=Depends(get_current_user)):
    """Return performance profile for a task."""
    report = performance_profiler.profile_execution(task_id)
    return {
        "task_id": report.task_id,
        "total_duration_ms": report.total_duration_ms,
        "bottleneck": report.bottleneck,
        "optimization_suggestions": report.optimization_suggestions,
        "step_latencies": [
            {
                "step_name": s.step_name,
                "latency_ms": s.latency_ms,
                "timestamp": s.timestamp,
                "metadata": s.metadata,
            }
            for s in report.step_latencies
        ]
    }


@router.get("/resources")
async def get_resource_usage(current_user=Depends(get_current_user)):
    """Return current resource usage and limits."""
    summary = await resource_limit_enforcer.get_usage_summary()
    return summary


@router.get("/cluster")
async def get_cluster_state(current_user=Depends(get_current_user)):
    """Return horizontal scaling cluster state."""
    state = await scaling_coordinator.get_cluster_state()
    return state
