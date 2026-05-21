from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from .anomaly import AnomalyDetector, AnomalySeverity, anomaly_detector
from .metrics import MetricsCollector, metrics_collector
from ..logs.logger import logger


class AlertChannel(str, Enum):
    LOG = "log"
    WEBHOOK = "webhook"
    EMAIL = "email"
    SLACK = "slack"


@dataclass
class Alert:
    severity: AnomalySeverity
    message: str
    triggered_rule: str
    timestamp: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    name: str
    metric: str
    threshold: float
    severity: AnomalySeverity
    channels: List[AlertChannel]
    cooldown_seconds: int = 300
    enabled: bool = True


class AlertManager:
    """Manages alert rules with severity levels and notification channels.

    Rules are evaluated against metrics; when triggered, alerts are dispatched
    to configured channels with cooldown protection.
    """

    def __init__(
        self,
        anomaly_detector: AnomalyDetector = None,
        metrics_collector: MetricsCollector = None
    ):
        self.anomaly_detector = anomaly_detector or AnomalyDetector()
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.rules: List[AlertRule] = []
        self._last_triggered: Dict[str, str] = {}
        self._alert_history: List[Alert] = []

        # Default rules
        self.add_rule(AlertRule(
            name="high_error_rate",
            metric="error_rate",
            threshold=0.2,
            severity=AnomalySeverity.WARNING,
            channels=[AlertChannel.LOG]
        ))
        self.add_rule(AlertRule(
            name="critical_error_rate",
            metric="error_rate",
            threshold=0.5,
            severity=AnomalySeverity.CRITICAL,
            channels=[AlertChannel.LOG]
        ))
        self.add_rule(AlertRule(
            name="high_latency",
            metric="latency_ms",
            threshold=30000,
            severity=AnomalySeverity.WARNING,
            channels=[AlertChannel.LOG]
        ))
        self.add_rule(AlertRule(
            name="cost_spike",
            metric="cost_usd",
            threshold=5.0,
            severity=AnomalySeverity.WARNING,
            channels=[AlertChannel.LOG]
        ))

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        for i, r in enumerate(self.rules):
            if r.name == name:
                self.rules.pop(i)
                return True
        return False

    def _is_on_cooldown(self, rule: AlertRule) -> bool:
        last = self._last_triggered.get(rule.name)
        if not last:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
            return (datetime.now(timezone.utc) - last_dt).total_seconds() < rule.cooldown_seconds
        except Exception:
            return False

    def _dispatch(self, alert: Alert, channels: List[AlertChannel]):
        for channel in channels:
            if channel == AlertChannel.LOG:
                level = "warning" if alert.severity == AnomalySeverity.WARNING else "error" if alert.severity == AnomalySeverity.CRITICAL else "info"
                getattr(logger, level)(f"ALERT [{alert.severity.upper()}] {alert.message} (rule: {alert.triggered_rule})")
            elif channel == AlertChannel.WEBHOOK:
                logger.info(f"Would dispatch webhook alert: {alert.message}")
            elif channel == AlertChannel.EMAIL:
                logger.info(f"Would dispatch email alert: {alert.message}")
            elif channel == AlertChannel.SLACK:
                logger.info(f"Would dispatch slack alert: {alert.message}")

    def evaluate(self, metrics: Optional[Dict[str, float]] = None) -> List[Alert]:
        """Evaluate all rules and return triggered alerts."""
        triggered: List[Alert] = []

        report = self.anomaly_detector.analyze()
        metric_values = metrics or {}

        # Map anomalies to metrics
        for anomaly in report.anomalies:
            metric_values[anomaly.metric] = anomaly.observed_value

        for rule in self.rules:
            if not rule.enabled or rule.metric not in metric_values:
                continue
            if self._is_on_cooldown(rule):
                continue

            value = metric_values[rule.metric]
            if value >= rule.threshold:
                self._last_triggered[rule.name] = datetime.now(timezone.utc).isoformat()
                alert = Alert(
                    severity=rule.severity,
                    message=f"{rule.metric}={value:.4f} exceeded threshold {rule.threshold}",
                    triggered_rule=rule.name,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    context={"metric": rule.metric, "value": value, "threshold": rule.threshold}
                )
                self._alert_history.append(alert)
                self._dispatch(alert, rule.channels)
                triggered.append(alert)

        return triggered

    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        return self._alert_history[-limit:]

    def clear_history(self):
        self._alert_history.clear()


# Module-level singleton
alert_manager = AlertManager(anomaly_detector=anomaly_detector, metrics_collector=metrics_collector)
