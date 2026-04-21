from typing import Dict, Any, List, Optional, Awaitable
from uuid import UUID, uuid4
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
    def __init__(self):
        self.spans: Dict[str, Span] = {}
        self.trace_index: Dict[str, List[str]] = {}
    
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
        
        try:
            import asyncio

            async def _persist_span() -> None:
                persisted = await span_repo.create(trace_id, span_id, operation, agent_name, metadata or {})
                self.spans[span_id] = span
                if trace_id not in self.trace_index:
                    self.trace_index[trace_id] = []
                if span_id not in self.trace_index[trace_id]:
                    self.trace_index[trace_id].append(span_id)
                return persisted

            try:
                asyncio.get_running_loop()
                asyncio.create_task(_persist_span())
            except RuntimeError:
                pass
        except Exception:
            pass
        
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

            try:
                import asyncio

                async def _persist_span_end() -> None:
                    await span_repo.update(span_id, status=status, error=error)

                try:
                    asyncio.get_running_loop()
                    asyncio.create_task(_persist_span_end())
                except RuntimeError:
                    pass
            except Exception:
                pass
    
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
        raise RuntimeError("Trace duration is unavailable without DB read path")
    
    def clear_trace(self, trace_id: str):
        span_ids = self.trace_index.pop(trace_id, [])
        for sid in span_ids:
            self.spans.pop(sid, None)


trace_manager = TraceManager()
