"""Phase 3.5 — Agent Feedback Loop: Learning from past executions.

Records, analyzes, and applies feedback from agent executions to improve
future performance. Tracks execution history, extracts patterns, and provides
insights for better planning and execution.

Spec: Build Plan Task 3.2.5, Section 6.2
Input Contract:  record_feedback(FeedbackRecord) → None
                 apply_learning(task_context) → LearningContext
Output Contract: LearningContext with relevant past insights for current task
"""

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType
from .base import AgentStatus


# ── Pydantic Models ──────────────────────────────────────────────────────────

class FeedbackType(str, Enum):
    """Types of feedback that can be collected."""
    EXECUTION_RESULT = "execution_result"
    USER_RATING = "user_rating"
    ERROR_PATTERN = "error_pattern"
    TOOL_PERFORMANCE = "tool_performance"
    AGENT_HANDOFF = "agent_handoff"
    PLAN_QUALITY = "plan_quality"
    VERIFICATION_RESULT = "verification_result"
    MANUAL_CORRECTION = "manual_correction"


class FeedbackRecord(BaseModel):
    """A single feedback record from agent execution."""

    record_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    agent_id: Optional[str] = None
    feedback_type: FeedbackType = FeedbackType.EXECUTION_RESULT
    status: AgentStatus = AgentStatus.PENDING
    output_data: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    recoverable: Optional[bool] = None
    duration_ms: float = 0.0
    token_usage: Dict[str, int] = Field(default_factory=dict)
    tool_calls_count: int = 0
    retry_count: int = 0
    confidence: float = 0.0
    user_rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LearningInsight(BaseModel):
    """A learned insight extracted from feedback history."""

    insight_id: str = Field(default_factory=lambda: str(uuid4()))
    pattern: str = Field(..., description="The pattern or insight discovered")
    category: str = Field(default="general", description="Category: tool, plan, error, agent")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    occurrences: int = 1
    last_seen: Optional[str] = None
    source_task_ids: List[str] = Field(default_factory=list)
    suggestion: Optional[str] = None


class LearningContext(BaseModel):
    """Context enriched with learnings from past executions.

    Returned by apply_learning() to provide relevant insights for the current task.
    """

    task_id: str
    query_hint: str = ""
    relevant_insights: List[LearningInsight] = Field(default_factory=list)
    recommended_tools: List[str] = Field(default_factory=list)
    recommended_avoid_tools: List[str] = Field(default_factory=list)
    success_rate_estimate: float = 0.0
    common_errors: List[str] = Field(default_factory=list)
    context_notes: List[str] = Field(default_factory=list)


class FeedbackSummary(BaseModel):
    """Aggregated summary of feedback records."""

    total_records: int = 0
    success_count: int = 0
    failure_count: int = 0
    average_duration_ms: float = 0.0
    average_confidence: float = 0.0
    average_user_rating: float = 0.0
    top_errors: List[Dict[str, Any]] = Field(default_factory=list)
    top_tools: List[Dict[str, Any]] = Field(default_factory=list)
    insights_count: int = 0
    recent_trend: str = "stable"  # improving, declining, stable


# ── FeedbackLoop ─────────────────────────────────────────────────────────────

class AgentFeedbackLoop:
    """Collects, analyzes, and applies feedback from agent executions.

    The feedback loop operates in three phases:
    1. Record: Capture execution results, errors, and user feedback.
    2. Analyze: Extract patterns and insights from stored records.
    3. Apply: Provide relevant learnings to new tasks for improved execution.

    Records are stored in-memory with optional persistence to PostgreSQL
    via ContextModel (generic KV store).
    """

    def __init__(self, max_records: int = 1000, insight_threshold: int = 3):
        """Initialize the feedback loop.

        Args:
            max_records: Maximum in-memory records before pruning.
            insight_threshold: Minimum occurrences before generating an insight.
        """
        self._records: Dict[str, FeedbackRecord] = {}
        self._insights: Dict[str, LearningInsight] = {}
        self._max_records = max_records
        self._insight_threshold = insight_threshold
        self._error_patterns: Dict[str, int] = {}  # error_type → count
        self._tool_stats: Dict[str, Dict[str, Any]] = {}  # tool → stats

    # ── Record Phase ─────────────────────────────────────────────────────

    async def record(self, record: FeedbackRecord) -> str:
        """Record feedback from an agent execution.

        Args:
            record: The FeedbackRecord to store.

        Returns:
            The record_id of the stored record.
        """
        self._records[record.record_id] = record

        # Update error patterns
        if record.error_type:
            self._error_patterns[record.error_type] = (
                self._error_patterns.get(record.error_type, 0) + 1
            )

        # Update tool stats
        tools = record.metadata.get("tools_used", [])
        for tool_name in tools:
            if tool_name not in self._tool_stats:
                self._tool_stats[tool_name] = {
                    "successes": 0,
                    "failures": 0,
                    "total_duration_ms": 0.0,
                    "calls": 0,
                }
            stats = self._tool_stats[tool_name]
            stats["calls"] += 1
            stats["total_duration_ms"] += record.duration_ms
            if record.status == AgentStatus.SUCCESS:
                stats["successes"] += 1
            else:
                stats["failures"] += 1

        # Prune if over limit (FIFO)
        if len(self._records) > self._max_records:
            oldest = sorted(self._records.keys())[0]
            del self._records[oldest]

        # Optionally persist to PostgreSQL
        try:
            await self._persist_record(record)
        except Exception as e:
            logger.debug(f"FeedbackLoop: Could not persist record (non-fatal): {e}")

        logger.debug(
            f"FeedbackLoop: Recorded feedback {record.record_id} "
            f"(task={record.task_id}, type={record.feedback_type.value}, "
            f"status={record.status.value})"
        )

        return record.record_id

    async def record_batch(self, records: List[FeedbackRecord]) -> List[str]:
        """Record multiple feedback entries at once.

        Args:
            records: List of FeedbackRecords.

        Returns:
            List of record_ids.
        """
        ids = []
        for record in records:
            rid = await self.record(record)
            ids.append(rid)
        return ids

    # ── Analyze Phase ────────────────────────────────────────────────────

    async def analyze(self) -> List[LearningInsight]:
        """Analyze stored feedback to extract learning insights.

        Insights are generated when a pattern appears at least
        self._insight_threshold times.

        Returns:
            List of new or updated LearningInsights.
        """
        new_insights: List[LearningInsight] = []

        # 1. Error pattern insights
        for error_type, count in self._error_patterns.items():
            if count >= self._insight_threshold:
                key = f"error:{error_type}"
                if key not in self._insights:
                    insight = LearningInsight(
                        pattern=f"Recurring error: {error_type}",
                        category="error",
                        confidence=min(0.9, count / 10),
                        occurrences=count,
                        suggestion=f"Consider adding specific handling for '{error_type}' errors",
                    )
                    self._insights[key] = insight
                    new_insights.append(insight)
                else:
                    self._insights[key].occurrences = count
                    self._insights[key].confidence = min(0.9, count / 10)

        # 2. Tool performance insights
        for tool_name, stats in self._tool_stats.items():
            total = stats["calls"]
            if total >= self._insight_threshold:
                fail_rate = stats["failures"] / total if total > 0 else 0
                key = f"tool:{tool_name}"

                if fail_rate > 0.3 and key not in self._insights:
                    insight = LearningInsight(
                        pattern=f"High failure rate for tool '{tool_name}' ({fail_rate:.1%})",
                        category="tool",
                        confidence=min(0.9, total / 20),
                        occurrences=total,
                        suggestion=f"Consider fallback tools for '{tool_name}' or investigate failures",
                    )
                    self._insights[key] = insight
                    new_insights.append(insight)
                elif fail_rate < 0.1 and key not in self._insights:
                    insight = LearningInsight(
                        pattern=f"Reliable tool: '{tool_name}' (success rate {1-fail_rate:.1%})",
                        category="tool",
                        confidence=min(0.9, total / 10),
                        occurrences=total,
                        suggestion=f"'{tool_name}' is a preferred choice for similar tasks",
                    )
                    self._insights[key] = insight
                    new_insights.append(insight)

        # 3. Confidence vs success insights
        high_conf_fails = [
            r for r in self._records.values()
            if r.confidence > 0.8 and r.status == AgentStatus.FAILURE
        ]
        if len(high_conf_fails) >= self._insight_threshold:
            key = "pattern:high_confidence_failures"
            if key not in self._insights:
                self._insights[key] = LearningInsight(
                    pattern="High-confidence predictions failing",
                    category="agent",
                    confidence=0.7,
                    occurrences=len(high_conf_fails),
                    suggestion="Agents may be overconfident; review verification thresholds",
                )
                new_insights.append(self._insights[key])

        logger.info(
            f"FeedbackLoop: Analysis complete — {len(new_insights)} new insights, "
            f"{len(self._insights)} total"
        )

        return new_insights

    # ── Apply Phase ──────────────────────────────────────────────────────

    async def apply_learning(
        self,
        task_id: str,
        query_hint: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> LearningContext:
        """Apply learnings to enrich context for a new task.

        Analyzes feedback history and provides relevant insights, tool
        recommendations, and success rate estimates.

        Args:
            task_id: The ID of the current task.
            query_hint: Hint about the task query for relevance matching.
            context: Additional task context.

        Returns:
            LearningContext enriched with relevant past insights.
        """
        # Run analysis to refresh insights
        await self.analyze()

        # Filter insights relevant to this task
        relevant: List[LearningInsight] = []
        for insight in self._insights.values():
            # Simple relevance: check if query hint matches pattern keywords
            if query_hint and any(
                word.lower() in insight.pattern.lower()
                for word in query_hint.split()[:5]
            ):
                relevant.append(insight)
            elif insight.category == "error":
                # Always include error insights
                relevant.append(insight)

        # Tool recommendations based on past success
        recommended: List[str] = []
        avoid: List[str] = []
        for tool_name, stats in self._tool_stats.items():
            total = stats["calls"]
            if total >= 3:
                fail_rate = stats["failures"] / total if total > 0 else 0
                if fail_rate < 0.1:
                    recommended.append(tool_name)
                elif fail_rate > 0.5:
                    avoid.append(tool_name)

        # Success rate estimate
        total = len(self._records)
        successes = sum(
            1 for r in self._records.values()
            if r.status == AgentStatus.SUCCESS
        )
        success_rate = successes / total if total > 0 else 0.5

        # Common errors
        sorted_errors = sorted(
            self._error_patterns.items(), key=lambda x: x[1], reverse=True
        )
        common_errors = [err for err, _ in sorted_errors[:5]]

        # Context notes
        notes: List[str] = []
        if success_rate < 0.5:
            notes.append("Overall success rate is below 50%; consider human review")
        if len(recommended) > 0:
            notes.append(f"Recommended tools: {', '.join(recommended[:5])}")
        if len(avoid) > 0:
            notes.append(f"Tools to avoid: {', '.join(avoid[:5])}")

        return LearningContext(
            task_id=task_id,
            query_hint=query_hint,
            relevant_insights=relevant[:10],
            recommended_tools=recommended[:10],
            recommended_avoid_tools=avoid[:5],
            success_rate_estimate=round(success_rate, 3),
            common_errors=common_errors,
            context_notes=notes,
        )

    # ── Query ────────────────────────────────────────────────────────────

    def get_record(self, record_id: str) -> Optional[FeedbackRecord]:
        """Get a specific feedback record by ID."""
        return self._records.get(record_id)

    def get_records_by_task(self, task_id: str) -> List[FeedbackRecord]:
        """Get all feedback records for a given task."""
        return [r for r in self._records.values() if r.task_id == task_id]

    def get_records_by_type(self, feedback_type: FeedbackType) -> List[FeedbackRecord]:
        """Get all records of a given feedback type."""
        return [r for r in self._records.values() if r.feedback_type == feedback_type]

    async def get_summary(self) -> FeedbackSummary:
        """Get an aggregated summary of all feedback records."""
        records = list(self._records.values())
        total = len(records)

        if total == 0:
            return FeedbackSummary()

        successes = sum(1 for r in records if r.status == AgentStatus.SUCCESS)
        failures = sum(1 for r in records if r.status == AgentStatus.FAILURE)
        avg_duration = (
            sum(r.duration_ms for r in records) / total if total > 0 else 0
        )
        avg_confidence = (
            sum(r.confidence for r in records) / total if total > 0 else 0
        )
        ratings = [r.user_rating for r in records if r.user_rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0

        # Top errors
        top_errors = sorted(
            [
                {"error_type": etype, "count": count}
                for etype, count in self._error_patterns.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        # Top tools
        top_tools = sorted(
            [
                {"tool": tname, **stats}
                for tname, stats in self._tool_stats.items()
            ],
            key=lambda x: x["calls"],
            reverse=True,
        )[:5]

        # Recent trend: compare last 20 vs previous 20
        recent = sorted(records, key=lambda r: r.recorded_at)[-20:]
        recent_successes = sum(1 for r in recent if r.status == AgentStatus.SUCCESS)
        recent_rate = recent_successes / len(recent) if recent else 0

        trend = "stable"
        if recent and successes / total > 0:
            if recent_rate > successes / total * 1.2:
                trend = "improving"
            elif recent_rate < successes / total * 0.8:
                trend = "declining"

        return FeedbackSummary(
            total_records=total,
            success_count=successes,
            failure_count=failures,
            average_duration_ms=round(avg_duration, 1),
            average_confidence=round(avg_confidence, 3),
            average_user_rating=round(avg_rating, 2),
            top_errors=top_errors,
            top_tools=top_tools,
            insights_count=len(self._insights),
            recent_trend=trend,
        )

    def get_all_insights(self) -> Dict[str, LearningInsight]:
        """Get all extracted learning insights."""
        return dict(self._insights)

    def reset(self) -> None:
        """Reset all stored feedback and insights."""
        self._records.clear()
        self._insights.clear()
        self._error_patterns.clear()
        self._tool_stats.clear()
        logger.info("FeedbackLoop: All records and insights cleared")

    # ── Internal ─────────────────────────────────────────────────────────

    async def _persist_record(self, record: FeedbackRecord) -> None:
        """Persist a feedback record to PostgreSQL via ContextModel.

        Args:
            record: The FeedbackRecord to persist.
        """
        try:
            from ..memory.models import ContextModel
            from ..memory.long_term import get_db_session

            async with get_db_session() as session:
                ctx = ContextModel(
                    key=f"feedback:{record.record_id}",
                    value=record.model_dump_json(),
                    category="feedback_record",
                    ttl=86400 * 30,  # 30 days
                )
                session.add(ctx)
                await session.commit()
        except ImportError:
            pass  # Database not available
        except Exception as e:
            logger.debug(f"FeedbackLoop: Persist failed (non-fatal): {e}")


# ── Singleton ────────────────────────────────────────────────────────────────

_feedback_loop_instance: Optional[AgentFeedbackLoop] = None


def get_feedback_loop(
    max_records: int = 1000,
    insight_threshold: int = 3,
) -> AgentFeedbackLoop:
    """Get or create the singleton AgentFeedbackLoop instance.

    Args:
        max_records: Max in-memory records (only used on first call).
        insight_threshold: Min occurrences for insight (only used on first call).

    Returns:
        The global AgentFeedbackLoop instance.
    """
    global _feedback_loop_instance
    if _feedback_loop_instance is None:
        _feedback_loop_instance = AgentFeedbackLoop(
            max_records=max_records,
            insight_threshold=insight_threshold,
        )
    return _feedback_loop_instance
