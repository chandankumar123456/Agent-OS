from typing import Dict, Any
from collections import defaultdict


class MetricsCollector:
    """Prometheus-compatible metrics collector.

    Provides counters and histograms for key system metrics.
    """

    def __init__(self):
        self._counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._histograms: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))

    def inc_counter(self, name: str, labels: Dict[str, str] = None, value: int = 1):
        label_key = ",".join(f'{k}="{v}"' for k, v in sorted((labels or {}).items()))
        self._counters[name][label_key] += value

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        label_key = ",".join(f'{k}="{v}"' for k, v in sorted((labels or {}).items()))
        self._histograms[name][label_key].append(value)

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

        return {
            "requests_total": requests_total,
            "errors_total": errors_total,
            "error_rate": error_rate,
            "avg_response_time": avg_response_time,
        }

    def reset(self):
        self._counters.clear()
        self._histograms.clear()


# Module-level singleton
metrics_collector = MetricsCollector()
