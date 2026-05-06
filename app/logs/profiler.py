from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import statistics


@dataclass
class StepProfile:
    step_name: str
    latency_ms: float
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfileReport:
    task_id: str
    total_duration_ms: float
    step_latencies: List[StepProfile]
    bottleneck: Optional[str]
    optimization_suggestions: List[str]


class PerformanceProfiler:
    """Identifies bottlenecks in execution: LLM latency, tool latency, orchestration overhead.

    Profiles per-step latency and provides actionable optimization suggestions.
    """

    def __init__(self):
        self._profiles: Dict[str, List[StepProfile]] = {}
        self._task_start_times: Dict[str, datetime] = {}

    def start_task(self, task_id: str):
        self._task_start_times[task_id] = datetime.utcnow()
        self._profiles[task_id] = []

    def record_step(
        self,
        task_id: str,
        step_name: str,
        latency_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        if task_id not in self._profiles:
            self._profiles[task_id] = []
        self._profiles[task_id].append(StepProfile(
            step_name=step_name,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata or {}
        ))

    def profile_execution(self, task_id: str) -> ProfileReport:
        """Generate a profile report for a completed task."""
        steps = self._profiles.get(task_id, [])
        start_time = self._task_start_times.get(task_id)

        if start_time:
            total_duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        else:
            total_duration_ms = sum(s.latency_ms for s in steps)

        # Find bottleneck
        bottleneck = None
        if steps:
            max_latency = max(s.latency_ms for s in steps)
            bottleneck_step = next(s for s in steps if s.latency_ms == max_latency)
            if max_latency > total_duration_ms * 0.3:
                bottleneck = bottleneck_step.step_name

        suggestions: List[str] = []

        # LLM latency suggestions
        llm_steps = [s for s in steps if "llm" in s.step_name.lower() or "planner" in s.step_name.lower()]
        if llm_steps:
            avg_llm = statistics.mean(s.latency_ms for s in llm_steps)
            if avg_llm > 5000:
                suggestions.append(f"LLM calls are slow (avg {avg_llm:.0f}ms). Consider caching or switching to a faster model.")

        # Tool latency suggestions
        tool_steps = [s for s in steps if "tool" in s.step_name.lower() or "execute" in s.step_name.lower()]
        if tool_steps:
            avg_tool = statistics.mean(s.latency_ms for s in tool_steps)
            if avg_tool > 3000:
                suggestions.append(f"Tool execution is slow (avg {avg_tool:.0f}ms). Review tool implementations or add timeouts.")

        # Orchestration overhead
        if steps and total_duration_ms > 0:
            step_sum = sum(s.latency_ms for s in steps)
            overhead = total_duration_ms - step_sum
            if overhead > total_duration_ms * 0.2:
                suggestions.append(f"High orchestration overhead ({overhead:.0f}ms). Consider reducing context serialization or checkpoint frequency.")

        # Too many steps
        if len(steps) > 20:
            suggestions.append(f"Task has many steps ({len(steps)}). Consider breaking into sub-tasks or using workflow mode.")

        return ProfileReport(
            task_id=task_id,
            total_duration_ms=total_duration_ms,
            step_latencies=steps,
            bottleneck=bottleneck,
            optimization_suggestions=suggestions
        )

    def get_task_ids(self) -> List[str]:
        return list(self._profiles.keys())

    def reset(self):
        self._profiles.clear()
        self._task_start_times.clear()


# Module-level singleton
performance_profiler = PerformanceProfiler()
