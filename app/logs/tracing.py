from typing import Dict, Any, List, Optional
from uuid import uuid4
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.long_term import trace_repo, span_repo


@dataclass
class Span:
    span_id: str
    trace_id: str
    operation: str
    agent_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    error: Optional[str] = None


class TraceManager:
    """Manages execution spans with transactional persistence.

    Spans are buffered in memory and can be persisted on demand.
    This allows the orchestrator to commit spans in the same
    database transaction as task state updates.
    """

    def __init__(self):
        self.spans: Dict[str, Span] = {}
        self.trace_index: Dict[str, List[str]] = {}
        self._pending_db_ops: List[dict] = []

    @staticmethod
    def _status_label(status: str) -> str:
        return status.lower() if isinstance(status, str) else status

    def start_span(
        self,
        trace_id: str,
        operation: str,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        span_id = str(uuid4())

        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            operation=operation,
            agent_name=agent_name,
            start_time=datetime.utcnow(),
            metadata=metadata or {}
        )

        self.spans[span_id] = span
        if trace_id not in self.trace_index:
            self.trace_index[trace_id] = []
        if span_id not in self.trace_index[trace_id]:
            self.trace_index[trace_id].append(span_id)

        return span_id

    def end_span(
        self,
        span_id: str,
        status: str = "success",
        error: Optional[str] = None
    ):
        if span_id in self.spans:
            span = self.spans[span_id]
            span.end_time = datetime.utcnow()
            span.status = status
            span.error = error

    async def persist_span(self, span_id: str) -> None:
        """Persist a single span to the database."""
        if span_id not in self.spans:
            return
        span = self.spans[span_id]
        await span_repo.create(
            span.trace_id,
            span.span_id,
            span.operation,
            span.agent_name,
            span.metadata
        )
        if span.end_time:
            await span_repo.update(span_id, status=self._status_label(span.status), error=span.error)

    async def persist_trace(self, trace_id: str) -> None:
        """Persist all spans for a trace to the database."""
        span_ids = self.trace_index.get(trace_id, [])
        for span_id in span_ids:
            await self.persist_span(span_id)

    def get_trace(self, trace_id: str) -> List[Span]:
        span_ids = self.trace_index.get(trace_id, [])
        return [self.spans[sid] for sid in span_ids if sid in self.spans]

    async def get_trace_db(self, trace_id: str) -> List[Span]:
        trace_row = await trace_repo.get_by_trace_id(trace_id)
        if not trace_row:
            return []

        db_spans = await span_repo.get_by_trace(trace_id)
        spans: List[Span] = []
        for span in db_spans:
            spans.append(
                Span(
                    span_id=span.span_id,
                    trace_id=span.trace_id,
                    operation=span.operation,
                    agent_name=span.agent_name,
                    start_time=span.start_time,
                    end_time=span.end_time,
                    metadata=span.metadata_json or {},
                    status=span.status,
                    error=span.error,
                )
            )
        return spans

    def get_trace_duration(self, trace_id: str) -> float:
        spans = self.get_trace(trace_id)
        if not spans:
            return 0.0
        start_times = [s.start_time for s in spans if s.start_time]
        end_times = [s.end_time for s in spans if s.end_time]
        if not start_times or not end_times:
            return 0.0
        return (max(end_times) - min(start_times)).total_seconds()


# Module-level singleton for backward compatibility
trace_manager = TraceManager()
