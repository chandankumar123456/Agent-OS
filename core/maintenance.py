"""Data retention and maintenance tasks for AgentOS.

Provides cleanup functions for purging old traces, spans, checkpoints,
and completed tasks to prevent unbounded storage growth.
"""
from datetime import datetime, timezone, timedelta
from .memory.long_term import db
from .logs.logger import logger


async def purge_old_data(retention_days: int = 30) -> dict:
    """Purge data older than retention_days.

    Args:
        retention_days: Age threshold for data deletion (default 30)

    Returns:
        dict with counts of deleted records per table
    """
    from sqlalchemy import text
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    results = {}

    tables = [
        ("spans", "spans", "start_time"),
        ("traces", "traces", "created_at"),
        ("node_traces", "node_traces", "created_at"),
        ("token_usage", "token_usage", "created_at"),
        ("checkpoints", "checkpoints", "created_at"),
        ("checkpoint_writes", "checkpoint_writes", "created_at"),
    ]

    async with db.engine.begin() as conn:
        for name, table, column in tables:
            try:
                result = await conn.execute(
                    text(f"DELETE FROM {table} WHERE {column} < :cutoff"),
                    {"cutoff": cutoff}
                )
                results[name] = result.rowcount
                logger.info(f"Purged {result.rowcount} records from {table}")
            except Exception as e:
                logger.warning(f"Failed to purge {table}: {e}")
                results[name] = str(e)

    # Also clean up completed/failed tasks older than retention
    try:
        result = await conn.execute(
            text("""
                DELETE FROM tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                AND updated_at < :cutoff
            """),
            {"cutoff": cutoff}
        )
        results["tasks"] = result.rowcount
        logger.info(f"Purged {result.rowcount} old tasks")
    except Exception as e:
        logger.warning(f"Failed to purge old tasks: {e}")
        results["tasks_error"] = str(e)

    return results


async def get_storage_stats() -> dict:
    """Get approximate record counts for all major tables."""
    from sqlalchemy import text
    stats = {}
    tables = ["tasks", "steps", "traces", "spans", "node_traces", "token_usage",
              "workflows", "workflow_nodes", "workflow_edges", "checkpoints",
              "checkpoint_writes", "tools_v2", "agents", "agent_versions"]

    async with db.engine.begin() as conn:
        for table in tables:
            try:
                result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                stats[table] = result.scalar()
            except Exception:
                stats[table] = None

    return stats
