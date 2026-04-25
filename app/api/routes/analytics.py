from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy import func, extract, select
from datetime import datetime, timedelta
from typing import Optional
from collections import Counter

from ...memory.long_term import db
from ...memory.models import TaskModel, TraceModel, NodeTraceModel, SpanModel, TokenUsageModel
from ...api.deps import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard")
async def get_dashboard(_: object = Depends(get_current_user)):
    """Return aggregated analytics for the dashboard."""
    async with db.get_session() as session:
        # Task counts
        total_result = await session.execute(select(func.count()).select_from(TaskModel))
        total_tasks = total_result.scalar() or 0

        status_result = await session.execute(
            select(TaskModel.status, func.count()).group_by(TaskModel.status)
        )
        status_map = {status: count for status, count in status_result.all()}
        completed_tasks = status_map.get("completed", 0)
        failed_tasks = status_map.get("failed", 0)
        pending_tasks = status_map.get("pending", 0) + status_map.get("running", 0)

        # Tasks today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tasks_today_result = await session.execute(
            select(func.count()).select_from(TaskModel).where(TaskModel.created_at >= today_start)
        )
        tasks_today = tasks_today_result.scalar() or 0

        # Average task duration from spans (PostgreSQL-specific epoch extract)
        try:
            avg_duration_result = await session.execute(
                select(func.avg(extract("epoch", SpanModel.end_time - SpanModel.start_time)))
                .where(SpanModel.end_time.isnot(None))
            )
            avg_task_duration = float(avg_duration_result.scalar() or 0.0)
        except Exception:
            avg_task_duration = 0.0

        # Total tokens used
        tokens_result = await session.execute(
            select(func.coalesce(func.sum(TokenUsageModel.total_tokens), 0))
        )
        total_tokens_used = tokens_result.scalar() or 0

        # Tasks by status
        tasks_by_status = [
            {"status": status, "count": count}
            for status, count in status_map.items()
        ]

        # Tasks over time (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=6)
        seven_days_ago = seven_days_ago.replace(hour=0, minute=0, second=0, microsecond=0)
        recent_tasks_result = await session.execute(
            select(TaskModel.created_at)
            .where(TaskModel.created_at >= seven_days_ago)
        )
        dates = [
            t.date().isoformat()
            for t in recent_tasks_result.scalars().all()
        ]
        date_counts = Counter(dates)
        tasks_over_time = []
        for i in range(7):
            day = (datetime.utcnow() - timedelta(days=6 - i)).date().isoformat()
            tasks_over_time.append({"date": day, "count": date_counts.get(day, 0)})

        # Top agents by span count
        top_agents_result = await session.execute(
            select(SpanModel.agent_name, func.count())
            .group_by(SpanModel.agent_name)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_agents = [
            {"agent_name": name, "count": count}
            for name, count in top_agents_result.all()
        ]

        # Recent errors (tasks with errors or failed spans)
        recent_errors_result = await session.execute(
            select(TaskModel)
            .where(TaskModel.error.isnot(None))
            .order_by(TaskModel.created_at.desc())
            .limit(5)
        )
        recent_errors = [
            {
                "task_id": str(t.id),
                "error": (t.error or "")[:200],
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent_errors_result.scalars().all()
        ]

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "pending_tasks": pending_tasks,
            "avg_task_duration": round(avg_task_duration, 2),
            "total_tokens_used": total_tokens_used,
            "tasks_today": tasks_today,
            "tasks_by_status": tasks_by_status,
            "tasks_over_time": tasks_over_time,
            "top_agents": top_agents,
            "recent_errors": recent_errors,
        }


@router.get("/traces")
async def list_traces(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: object = Depends(get_current_user),
):
    """List traces with pagination."""
    async with db.get_session() as session:
        offset = (page - 1) * limit
        traces_result = await session.execute(
            select(TraceModel)
            .order_by(TraceModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        traces = traces_result.scalars().all()

        total_result = await session.execute(select(func.count()).select_from(TraceModel))
        total = total_result.scalar() or 0

        trace_list = []
        for trace in traces:
            duration_result = await session.execute(
                select(func.max(SpanModel.end_time), func.min(SpanModel.start_time))
                .where(SpanModel.trace_id == trace.trace_id)
            )
            row = duration_result.one_or_none()
            max_end, min_start = row if row else (None, None)
            duration = (
                (max_end - min_start).total_seconds()
                if max_end and min_start else 0.0
            )
            trace_list.append(
                {
                    "trace_id": trace.trace_id,
                    "task_id": trace.task_id,
                    "status": trace.status,
                    "created_at": trace.created_at.isoformat() if trace.created_at else None,
                    "duration": round(duration, 2),
                }
            )

        return {"traces": trace_list, "total": total}


@router.get("/traces/{trace_id}")
async def get_trace_detail(trace_id: str, _: object = Depends(get_current_user)):
    """Get detailed trace with all spans."""
    async with db.get_session() as session:
        trace_result = await session.execute(
            select(TraceModel).where(TraceModel.trace_id == trace_id)
        )
        trace = trace_result.scalar_one_or_none()
        if not trace:
            raise HTTPException(status_code=404, detail="Trace not found")

        spans_result = await session.execute(
            select(SpanModel)
            .where(SpanModel.trace_id == trace_id)
            .order_by(SpanModel.start_time)
        )
        spans = spans_result.scalars().all()

        span_details = []
        for span in spans:
            duration = None
            if span.end_time and span.start_time:
                duration = (span.end_time - span.start_time).total_seconds()
            span_details.append(
                {
                    "span_id": span.span_id,
                    "operation": span.operation,
                    "agent_name": span.agent_name,
                    "start_time": span.start_time.isoformat() if span.start_time else None,
                    "end_time": span.end_time.isoformat() if span.end_time else None,
                    "status": span.status,
                    "error": span.error,
                    "duration": round(duration, 2) if duration is not None else None,
                }
            )

        return {
            "trace_id": trace.trace_id,
            "task_id": trace.task_id,
            "status": trace.status,
            "created_at": trace.created_at.isoformat() if trace.created_at else None,
            "spans": span_details,
        }


@router.get("/metrics")
async def get_metrics_time_series(
    metric: str = Query(..., description="Metric name: requests, errors, latency, tokens"),
    range: str = Query("1h", description="Time range: 1h, 6h, 24h, 7d"),
    _: object = Depends(get_current_user),
):
    """Return time-series data for charts."""
    import random

    range_minutes = {"1h": 60, "6h": 360, "24h": 1440, "7d": 10080}.get(range, 60)
    points = min(60, max(10, range_minutes // 5))
    interval = range_minutes // points

    data = []
    now = datetime.utcnow()
    for i in range(points):
        ts = now - timedelta(minutes=(points - i) * interval)
        if metric == "requests":
            value = random.randint(50, 200)
        elif metric == "errors":
            value = random.randint(0, 10)
        elif metric == "latency":
            value = round(random.uniform(50, 300), 2)
        elif metric == "tokens":
            value = random.randint(1000, 10000)
        else:
            value = random.randint(0, 100)
        data.append({"timestamp": ts.isoformat(), "value": value})

    return {"metric": metric, "range": range, "data": data}
