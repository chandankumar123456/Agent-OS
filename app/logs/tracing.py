from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from datetime import datetime
from dataclasses import dataclass, field


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
        
        self.spans[span_id] = span
        
        if trace_id not in self.trace_index:
            self.trace_index[trace_id] = []
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
    
    def get_trace(self, trace_id: str) -> List[Span]:
        span_ids = self.trace_index.get(trace_id, [])
        return [self.spans[sid] for sid in span_ids if sid in self.spans]
    
    def get_trace_duration(self, trace_id: str) -> float:
        spans = self.get_trace(trace_id)
        
        if not spans:
            return 0.0
        
        start = min(s.start_time for s in spans)
        end = max((s.end_time or datetime.utcnow()) for s in spans)
        
        return (end - start).total_seconds()
    
    def clear_trace(self, trace_id: str):
        span_ids = self.trace_index.pop(trace_id, [])
        for sid in span_ids:
            self.spans.pop(sid, None)


trace_manager = TraceManager()