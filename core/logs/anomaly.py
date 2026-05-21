from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import statistics


class AnomalySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    metric: str
    severity: AnomalySeverity
    observed_value: float
    expected_range: tuple
    message: str
    timestamp: str
    affected_tasks: List[str] = field(default_factory=list)


@dataclass
class AnomalyReport:
    anomalies: List[Anomaly]
    severity: AnomalySeverity
    affected_tasks: List[str]
    recommendations: List[str]


class AnomalyDetector:
    """Detects unusual patterns in metrics: error rate spikes, latency anomalies, infinite loops, cost outliers.

    Uses statistical thresholds (mean + N*stddev) over a sliding window.
    """

    def __init__(
        self,
        error_rate_threshold: float = 0.2,
        latency_threshold_ms: float = 30000,
        cost_threshold_usd: float = 5.0,
        loop_threshold: int = 3,
        window_size: int = 10
    ):
        self.error_rate_threshold = error_rate_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.cost_threshold_usd = cost_threshold_usd
        self.loop_threshold = loop_threshold
        self.window_size = window_size

        self._error_rates: List[float] = []
        self._latencies: List[float] = []
        self._costs: List[float] = []
        self._loop_counts: List[int] = []

    def record_error_rate(self, rate: float):
        self._error_rates.append(rate)
        if len(self._error_rates) > self.window_size:
            self._error_rates.pop(0)

    def record_latency(self, latency_ms: float):
        self._latencies.append(latency_ms)
        if len(self._latencies) > self.window_size:
            self._latencies.pop(0)

    def record_cost(self, cost_usd: float):
        self._costs.append(cost_usd)
        if len(self._costs) > self.window_size:
            self._costs.pop(0)

    def record_loop_count(self, count: int):
        self._loop_counts.append(count)
        if len(self._loop_counts) > self.window_size:
            self._loop_counts.pop(0)

    def _statistical_range(self, values: List[float], std_multiplier: float = 2.0) -> tuple:
        if len(values) < 2:
            return (0.0, float("inf"))
        mean = statistics.mean(values)
        try:
            std = statistics.stdev(values)
        except statistics.StatisticsError:
            std = 0.0
        return (max(0, mean - std_multiplier * std), mean + std_multiplier * std)

    def analyze(self, window: Optional[List[Dict[str, Any]]] = None) -> AnomalyReport:
        """Analyze current metrics for anomalies."""
        anomalies: List[Anomaly] = []
        affected_tasks: List[str] = []
        recommendations: List[str] = []

        # Error rate anomaly
        if self._error_rates:
            current_error = self._error_rates[-1]
            expected = self._statistical_range(self._error_rates[:-1]) if len(self._error_rates) > 1 else (0.0, self.error_rate_threshold)
            if current_error > self.error_rate_threshold or current_error > expected[1]:
                sev = AnomalySeverity.CRITICAL if current_error > 0.5 else AnomalySeverity.WARNING
                anomalies.append(Anomaly(
                    metric="error_rate",
                    severity=sev,
                    observed_value=current_error,
                    expected_range=expected,
                    message=f"Error rate spike: {current_error:.2%} (threshold: {self.error_rate_threshold:.0%})",
                    timestamp=datetime.now(timezone.utc).isoformat()
                ))
                recommendations.append("Investigate recent failures and check tool health.")

        # Latency anomaly
        if self._latencies:
            current_latency = self._latencies[-1]
            expected = self._statistical_range(self._latencies[:-1]) if len(self._latencies) > 1 else (0.0, self.latency_threshold_ms)
            if current_latency > self.latency_threshold_ms or current_latency > expected[1]:
                sev = AnomalySeverity.CRITICAL if current_latency > 60000 else AnomalySeverity.WARNING
                anomalies.append(Anomaly(
                    metric="latency_ms",
                    severity=sev,
                    observed_value=current_latency,
                    expected_range=expected,
                    message=f"Latency anomaly: {current_latency:.0f}ms (threshold: {self.latency_threshold_ms:.0f}ms)",
                    timestamp=datetime.now(timezone.utc).isoformat()
                ))
                recommendations.append("Check for slow LLM responses or tool timeouts.")

        # Cost anomaly
        if self._costs:
            current_cost = self._costs[-1]
            expected = self._statistical_range(self._costs[:-1]) if len(self._costs) > 1 else (0.0, self.cost_threshold_usd)
            if current_cost > self.cost_threshold_usd or current_cost > expected[1]:
                sev = AnomalySeverity.WARNING if current_cost > self.cost_threshold_usd else AnomalySeverity.INFO
                anomalies.append(Anomaly(
                    metric="cost_usd",
                    severity=sev,
                    observed_value=current_cost,
                    expected_range=expected,
                    message=f"Cost outlier: ${current_cost:.4f} (threshold: ${self.cost_threshold_usd:.2f})",
                    timestamp=datetime.now(timezone.utc).isoformat()
                ))
                recommendations.append("Review expensive tool invocations and enable caching.")

        # Loop anomaly
        if self._loop_counts:
            current_loop = self._loop_counts[-1]
            if current_loop >= self.loop_threshold:
                anomalies.append(Anomaly(
                    metric="loop_count",
                    severity=AnomalySeverity.CRITICAL,
                    observed_value=float(current_loop),
                    expected_range=(0.0, float(self.loop_threshold)),
                    message=f"Infinite loop detected: {current_loop} iterations (threshold: {self.loop_threshold})",
                    timestamp=datetime.now(timezone.utc).isoformat()
                ))
                recommendations.append("Abort task and investigate plan generation logic.")

        # Determine overall severity
        overall = AnomalySeverity.INFO
        for a in anomalies:
            if a.severity == AnomalySeverity.CRITICAL:
                overall = AnomalySeverity.CRITICAL
                break
            elif a.severity == AnomalySeverity.WARNING and overall == AnomalySeverity.INFO:
                overall = AnomalySeverity.WARNING

        return AnomalyReport(
            anomalies=anomalies,
            severity=overall,
            affected_tasks=affected_tasks,
            recommendations=recommendations
        )

    def reset(self):
        self._error_rates.clear()
        self._latencies.clear()
        self._costs.clear()
        self._loop_counts.clear()


# Module-level singleton
anomaly_detector = AnomalyDetector()
