import os
from typing import Dict, Any
from collections import defaultdict


def _is_desktop_mode() -> bool:
    mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
    return mode.lower() == "grpc"


class MetricsCollector:
    """Prometheus-compatible metrics collector.

    Provides counters and histograms for key system metrics.
    In desktop mode, also delegates to LocalMetrics for SQLite persistence.
    """

    def __init__(self):
        self._counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._histograms: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._local_metrics = None
        if _is_desktop_mode():
            try:
                from ..desktop_native.local_metrics import local_metrics
                self._local_metrics = local_metrics
            except Exception:
                pass

    def inc_counter(self, name: str, labels: Dict[str, str] = None, value: int = 1):
        label_key = ",".join(f'{k}="{v}"' for k, v in sorted((labels or {}).items()))
        self._counters[name][label_key] += value
        if self._local_metrics:
            try:
                self._local_metrics.inc_counter(name, labels, value)
            except Exception:
                pass

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        label_key = ",".join(f'{k}="{v}"' for k, v in sorted((labels or {}).items()))
        self._histograms[name][label_key].append(value)
        if self._local_metrics:
            try:
                self._local_metrics.observe_histogram(name, value, labels)
            except Exception:
                pass

    def get_prometheus_format(self) -> str:
        lines = []
        for name, label_dict in self._counters.items():
            lines.append(f"# TYPE {name} counter")
            for label_key, value in label_dict.items():
                if label_key:
                    lines.append(f'{name}{{{label_key}}} {value}')
                else:
                    lines.append(f'{name} {value}')
        for name, label_dict in self._histograms.items():
            lines.append(f"# TYPE {name} histogram")
            for label_key, values in label_dict.items():
                total = sum(values)
                count = len(values)
                if label_key:
                    lines.append(f'{name}_sum{{{label_key}}} {total}')
                    lines.append(f'{name}_count{{{label_key}}} {count}')
                else:
                    lines.append(f'{name}_sum {total}')
                    lines.append(f'{name}_count {count}')
        return "\n".join(lines)

    def record_desktop_task(self, task_id: str, duration_seconds: float, success: bool) -> None:
        """Record a desktop task execution with duration and outcome."""
        self.observe_histogram("desktop_task_duration", duration_seconds, {"success": str(success)})
        self.inc_counter("desktop_task_total", {"success": str(success)})

    def record_desktop_action(self, task_id: str, action_name: str) -> None:
        """Record a desktop action (e.g. click, type, launch)."""
        self.inc_counter("desktop_action_count", {"action": action_name})

    def record_desktop_retry(self, task_id: str, action_name: str) -> None:
        """Record a retry of a desktop action."""
        self.inc_counter("desktop_retry_count", {"action": action_name})

    def record_desktop_perception_layer(self, task_id: str, layer: str) -> None:
        """Record usage of a perception layer (e.g. screenshot, OCR, vision)."""
        self.inc_counter("desktop_perception_layer", {"layer": layer})

    def record_tokens(self, model: str, input_tokens: int, output_tokens: int):
        """Record token usage for a model invocation."""
        total = input_tokens + output_tokens
        self.inc_counter("tokens_total", {"model": model}, total)
        self.inc_counter("tokens_input_total", {"model": model}, input_tokens)
        self.inc_counter("tokens_output_total", {"model": model}, output_tokens)

    def get_json_summary(self) -> dict:
        """Return aggregated metrics as JSON for the dashboard."""
        requests_total = sum(self._counters.get("http_requests_total", {}).values())
        errors_total = sum(self._counters.get("http_errors_total", {}).values())
        error_rate = errors_total / requests_total if requests_total > 0 else 0.0

        histogram = self._histograms.get("http_request_duration_seconds", {})
        all_values = []
        for values in histogram.values():
            all_values.extend(values)
        avg_response_time = sum(all_values) / len(all_values) if all_values else 0.0

        tokens_total = sum(self._counters.get("tokens_total", {}).values())

        return {
            "requests_total": requests_total,
            "errors_total": errors_total,
            "error_rate": error_rate,
            "avg_response_time": avg_response_time,
            "tokens_total": tokens_total,
        }

    def reset(self):
        self._counters.clear()
        self._histograms.clear()


# Module-level singleton
metrics_collector = MetricsCollector()
