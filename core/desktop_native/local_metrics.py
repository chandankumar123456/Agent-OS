"""LocalMetrics — in-memory gauges with SQLite persistence for desktop-native mode.

Replaces Prometheus-oriented metrics with local-first diagnostics:
- In-memory counters and gauges for fast collection
- Periodic snapshots to SQLite for historical analysis
- Optional Prometheus export for power users
- No external dependencies

Usage:
    from core.desktop_native.local_metrics import local_metrics
    local_metrics.inc_counter("tasks_completed", {"status": "success"})
    local_metrics.set_gauge("memory_mb", 128.5)
    await local_metrics.snapshot()  # Persist to SQLite
"""

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from ..logs.logger import logger
from .sqlite_store import sqlite_store


@dataclass
class MetricValue:
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class LocalMetrics:
    """Desktop-native metrics collector with SQLite persistence."""

    def __init__(self, snapshot_interval_seconds: int = 60):
        self._counters: Dict[str, List[MetricValue]] = defaultdict(list)
        self._gauges: Dict[str, MetricValue] = {}
        self._histograms: Dict[str, List[MetricValue]] = defaultdict(list)
        self._snapshot_interval = snapshot_interval_seconds
        self._last_snapshot = 0.0
        self._lock = asyncio.Lock()
        self._sqlite = sqlite_store

    async def _ensure_table(self):
        try:
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS metrics_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    value REAL NOT NULL,
                    labels TEXT NOT NULL DEFAULT '{}',
                    timestamp TEXT NOT NULL
                )
            """)
            await self._sqlite.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_name_time
                ON metrics_snapshots(metric_name, timestamp)
            """)
            await self._sqlite.commit()
        except Exception as e:
            logger.warning(f"Failed to create metrics table: {e}")

    def inc_counter(self, name: str, labels: Optional[Dict[str, str]] = None, value: float = 1.0):
        """Increment a counter metric."""
        labels = labels or {}
        self._counters[name].append(MetricValue(value=value, timestamp=time.time(), labels=labels))

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        self._gauges[name] = MetricValue(value=value, timestamp=time.time(), labels=(labels or {}))

    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Observe a histogram value."""
        labels = labels or {}
        self._histograms[name].append(MetricValue(value=value, timestamp=time.time(), labels=labels))

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        values = self._counters.get(name, [])
        if labels:
            return sum(v.value for v in values if v.labels == labels)
        return sum(v.value for v in values)

    def get_gauge(self, name: str) -> Optional[float]:
        """Get current gauge value."""
        mv = self._gauges.get(name)
        return mv.value if mv else None

    def get_histogram_stats(self, name: str) -> Dict[str, Any]:
        """Get histogram statistics."""
        values = [v.value for v in self._histograms.get(name, [])]
        if not values:
            return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    async def snapshot(self) -> int:
        """Persist current metrics to SQLite. Returns count of metrics saved."""
        async with self._lock:
            await self._ensure_table()
            now = datetime.now(timezone.utc).isoformat()
            count = 0

            # Persist counters (aggregate by labels)
            for name, values in self._counters.items():
                if not values:
                    continue
                # Aggregate by label combination
                by_labels: Dict[str, float] = defaultdict(float)
                for v in values:
                    label_key = json.dumps(v.labels, sort_keys=True)
                    by_labels[label_key] += v.value
                for label_key, total in by_labels.items():
                    await self._sqlite.execute(
                        "INSERT INTO metrics_snapshots (metric_name, metric_type, value, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (name, "counter", total, label_key, now),
                    )
                    count += 1

            # Persist gauges
            for name, mv in self._gauges.items():
                await self._sqlite.execute(
                    "INSERT INTO metrics_snapshots (metric_name, metric_type, value, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (name, "gauge", mv.value, json.dumps(mv.labels, sort_keys=True), now),
                )
                count += 1

            # Persist histograms (aggregate stats)
            for name, values in self._histograms.items():
                if not values:
                    continue
                stats = self.get_histogram_stats(name)
                await self._sqlite.execute(
                    "INSERT INTO metrics_snapshots (metric_name, metric_type, value, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (name, "histogram_count", stats["count"], "{}", now),
                )
                await self._sqlite.execute(
                    "INSERT INTO metrics_snapshots (metric_name, metric_type, value, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (name, "histogram_sum", stats["sum"], "{}", now),
                )
                count += 2

            await self._sqlite.commit()

            # Clear in-memory data after snapshot
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._last_snapshot = time.time()

            return count

    async def maybe_snapshot(self) -> bool:
        """Snapshot if interval has passed."""
        if time.time() - self._last_snapshot >= self._snapshot_interval:
            await self.snapshot()
            return True
        return False

    def get_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        for name, values in self._counters.items():
            lines.append(f"# TYPE {name} counter")
            by_labels: Dict[str, float] = defaultdict(float)
            for v in values:
                label_key = json.dumps(v.labels, sort_keys=True)
                by_labels[label_key] += v.value
            for label_key, total in by_labels.items():
                labels_str = ",".join(f'{k}="{v}"' for k, v in json.loads(label_key).items())
                if labels_str:
                    lines.append(f'{name}{{{labels_str}}} {total}')
                else:
                    lines.append(f'{name} {total}')

        for name, mv in self._gauges.items():
            lines.append(f"# TYPE {name} gauge")
            labels_str = ",".join(f'{k}="{v}"' for k, v in (mv.labels or {}).items())
            if labels_str:
                lines.append(f'{name}{{{labels_str}}} {mv.value}')
            else:
                lines.append(f'{name} {mv.value}')

        return "\n".join(lines)

    async def query_history(self, metric_name: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """Query metric history from SQLite."""
        try:
            await self._ensure_table()
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
            rows = await self._sqlite.fetchall(
                "SELECT * FROM metrics_snapshots WHERE metric_name = ? AND timestamp > ? ORDER BY timestamp",
                (metric_name, cutoff),
            )
            return [
                {
                    "metric_name": r["metric_name"],
                    "metric_type": r["metric_type"],
                    "value": r["value"],
                    "labels": json.loads(r["labels"]),
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to query metric history: {e}")
            return []

    async def cleanup_old(self, max_age_days: int = 30) -> int:
        """Remove old metric snapshots. Returns count deleted."""
        try:
            await self._ensure_table()
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            cursor = await self._sqlite.execute(
                "DELETE FROM metrics_snapshots WHERE timestamp < ?",
                (cutoff,),
            )
            await self._sqlite.commit()
            count = cursor.rowcount if hasattr(cursor, "rowcount") else 0
            if count > 0:
                logger.info(f"Cleaned up {count} old metric snapshots")
            return count
        except Exception as e:
            logger.warning(f"Failed to cleanup old metrics: {e}")
            return 0


# Module-level singleton
local_metrics = LocalMetrics()
