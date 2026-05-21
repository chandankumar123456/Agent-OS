"""User memory profile for cross-task knowledge retrieval.

Stores user preferences, learned patterns, and task history to enable
personalized agent behavior across multiple task executions.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import BaseModel, Field

from .short_term import redis_client
from .long_term import db
from ..logs.logger import logger


class UserFact(BaseModel):
    """A single learned fact about a user."""
    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    category: str = Field(..., description="Category: preference, pattern, constraint, context")
    key: str = Field(..., description="Short fact key")
    value: str = Field(..., description="Fact value")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_task_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    access_count: int = Field(default=0)


class UserProfile(BaseModel):
    """Complete user memory profile."""
    user_id: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    learned_patterns: List[UserFact] = Field(default_factory=list)
    recent_task_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    context_summary: str = Field(default="")
    last_updated: Optional[datetime] = None


class UserMemoryProfile:
    """Manages per-user persistent memory profiles.

    Uses Redis for fast access and PostgreSQL for durability.
    Supports fact deduplication, relevance scoring, and pattern extraction.

    Usage:
        profile = UserMemoryProfile()
        await profile.record_fact(user_id, "preference", "editor", "vscode")
        facts = await profile.get_relevant_facts(user_id, "editor")
    """

    def __init__(
        self,
        max_facts_per_user: int = 500,
        fact_ttl_days: int = 90,
        redis_prefix: str = "agentos:profile:",
    ):
        self.max_facts_per_user = max_facts_per_user
        self.fact_ttl_days = fact_ttl_days
        self.redis_prefix = redis_prefix

    def _redis_key(self, user_id: str) -> str:
        return f"{self.redis_prefix}{user_id}"

    def _fact_redis_key(self, user_id: str, fact_id: str) -> str:
        return f"{self.redis_prefix}{user_id}:fact:{fact_id}"

    async def get_profile(self, user_id: str) -> UserProfile:
        """Retrieve a user's memory profile.

        Args:
            user_id: The user identifier.

        Returns:
            UserProfile (empty if not found).
        """
        redis_key = self._redis_key(user_id)
        try:
            data = await redis_client.get(redis_key)
            if data:
                return UserProfile(**data)
        except Exception as e:
            logger.warning(f"Redis profile read failed for {user_id}: {e}")

        # Fallback: try to build from PostgreSQL facts
        try:
            facts = await self._load_facts_from_db(user_id)
            if facts:
                profile = UserProfile(
                    user_id=user_id,
                    learned_patterns=facts,
                    last_updated=datetime.now(timezone.utc),
                )
                # Cache in Redis (best-effort)
                try:
                    await redis_client.set(redis_key, profile.model_dump(mode="json"), expire=self.fact_ttl_days * 86400)
                except Exception:
                    pass
                return profile
        except Exception as e:
            logger.warning(f"DB profile read failed for {user_id}: {e}")

        return UserProfile(user_id=user_id)

    async def record_fact(
        self,
        user_id: str,
        category: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        source_task_id: Optional[str] = None,
    ) -> UserFact:
        """Record a new fact about a user.

        Args:
            user_id: The user identifier.
            category: Fact category (preference, pattern, constraint, context).
            key: Short fact key.
            value: Fact value.
            confidence: Confidence score 0.0-1.0.
            source_task_id: Optional originating task ID.

        Returns:
            The recorded UserFact.
        """
        now = datetime.now(timezone.utc)
        fact = UserFact(
            category=category,
            key=key,
            value=value,
            confidence=confidence,
            source_task_id=source_task_id,
            created_at=now,
            updated_at=now,
        )

        # Update Redis profile
        profile = await self.get_profile(user_id)
        # Deduplicate: update existing fact with same category+key
        existing_idx = None
        for idx, f in enumerate(profile.learned_patterns):
            if f.category == category and f.key == key:
                existing_idx = idx
                break

        if existing_idx is not None:
            # Update existing fact, boost confidence
            old_fact = profile.learned_patterns[existing_idx]
            fact.confidence = min(1.0, max(old_fact.confidence, confidence) + 0.1)
            fact.created_at = old_fact.created_at
            profile.learned_patterns[existing_idx] = fact
        else:
            profile.learned_patterns.append(fact)

        # Prune if exceeded max
        if len(profile.learned_patterns) > self.max_facts_per_user:
            profile.learned_patterns = self._prune_facts(profile.learned_patterns)

        profile.last_updated = now
        profile.context_summary = await self._generate_context_summary(profile)

        await self._save_profile(user_id, profile)
        await self._save_fact_to_db(user_id, fact)

        logger.debug(f"Recorded fact for user {user_id}: {category}/{key}")
        return fact

    async def get_relevant_facts(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[UserFact]:
        """Retrieve facts relevant to a query string.

        Uses simple keyword matching + confidence scoring.

        Args:
            user_id: The user identifier.
            query: Query string to match against fact keys/values.
            top_k: Maximum number of facts to return.

        Returns:
            List of relevant UserFact objects, sorted by relevance.
        """
        profile = await self.get_profile(user_id)
        query_lower = query.lower()
        scored: List[Tuple[float, UserFact]] = []

        for fact in profile.learned_patterns:
            score = 0.0
            if query_lower in fact.key.lower():
                score += 2.0
            if query_lower in fact.value.lower():
                score += 1.0
            if query_lower in fact.category.lower():
                score += 0.5
            if score > 0:
                # Weight by confidence and recency
                age_days = (datetime.now(timezone.utc) - (fact.updated_at or fact.created_at or datetime.now(timezone.utc))).days
                recency_boost = max(0.5, 1.0 - (age_days / self.fact_ttl_days))
                final_score = score * fact.confidence * recency_boost
                scored.append((final_score, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:top_k]]

    async def record_task_summary(
        self,
        user_id: str,
        task_id: str,
        query: str,
        result_summary: str,
        tools_used: Optional[List[str]] = None,
    ) -> None:
        """Record a summary of a completed task for the user profile.

        Args:
            user_id: The user identifier.
            task_id: The task identifier.
            query: Original user query.
            result_summary: Brief summary of the result.
            tools_used: List of tool names used.
        """
        profile = await self.get_profile(user_id)
        summary = {
            "task_id": task_id,
            "query": query,
            "result_summary": result_summary,
            "tools_used": tools_used or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        profile.recent_task_summaries.insert(0, summary)
        # Keep only last 20
        profile.recent_task_summaries = profile.recent_task_summaries[:20]
        profile.last_updated = datetime.now(timezone.utc)
        await self._save_profile(user_id, profile)

    async def get_recent_task_summaries(
        self,
        user_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get recent task summaries for a user.

        Args:
            user_id: The user identifier.
            limit: Maximum number of summaries.

        Returns:
            List of task summary dicts.
        """
        profile = await self.get_profile(user_id)
        return profile.recent_task_summaries[:limit]

    async def update_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any],
    ) -> None:
        """Update user preferences dictionary.

        Args:
            user_id: The user identifier.
            preferences: Preference key-value pairs to update.
        """
        profile = await self.get_profile(user_id)
        profile.preferences.update(preferences)
        profile.last_updated = datetime.now(timezone.utc)
        await self._save_profile(user_id, profile)
        logger.debug(f"Updated preferences for user {user_id}: {list(preferences.keys())}")

    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user preferences.

        Args:
            user_id: The user identifier.

        Returns:
            Preference dictionary.
        """
        profile = await self.get_profile(user_id)
        return profile.preferences

    async def delete_profile(self, user_id: str) -> bool:
        """Delete a user's memory profile.

        Args:
            user_id: The user identifier.

        Returns:
            True if deleted, False otherwise.
        """
        redis_key = self._redis_key(user_id)
        try:
            await redis_client.delete(redis_key)
        except Exception as e:
            logger.warning(f"Redis profile delete failed for {user_id}: {e}")

        try:
            async with db.get_session() as session:
                from sqlalchemy import delete
                from .models import ContextModel
                await session.execute(
                    delete(ContextModel).where(ContextModel.task_id == f"user_profile:{user_id}")
                )
                await session.commit()
            return True
        except Exception as e:
            logger.error(f"DB profile delete failed for {user_id}: {e}")
            return False

    def _prune_facts(self, facts: List[UserFact]) -> List[UserFact]:
        """Prune facts to max limit, keeping highest confidence + most recent."""
        def sort_key(f: UserFact) -> Tuple[float, datetime]:
            ts = f.updated_at or f.created_at or datetime.min
            return (f.confidence, ts)

        facts.sort(key=sort_key, reverse=True)
        return facts[: self.max_facts_per_user]

    async def _generate_context_summary(self, profile: UserProfile) -> str:
        """Generate a brief text summary of the user's profile."""
        parts = []
        if profile.preferences:
            parts.append(f"Preferences: {len(profile.preferences)} entries")
        if profile.learned_patterns:
            parts.append(f"Learned patterns: {len(profile.learned_patterns)} facts")
        if profile.recent_task_summaries:
            parts.append(f"Recent tasks: {len(profile.recent_task_summaries)}")
        return "; ".join(parts) if parts else "No profile data yet"

    async def _save_profile(self, user_id: str, profile: UserProfile) -> None:
        """Save profile to Redis."""
        redis_key = self._redis_key(user_id)
        try:
            await redis_client.set(
                redis_key,
                profile.model_dump(mode="json"),
                expire=self.fact_ttl_days * 86400,
            )
        except Exception as e:
            logger.warning(f"Failed to save profile to Redis for {user_id}: {e}")

    async def _save_fact_to_db(self, user_id: str, fact: UserFact) -> None:
        """Persist a single fact to PostgreSQL for durability."""
        try:
            async with db.get_session() as session:
                from .models import ContextModel
                from sqlalchemy import select
                key = f"fact:{fact.category}:{fact.key}"
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.task_id == f"user_profile:{user_id}",
                        ContextModel.key == key,
                    )
                )
                existing = result.scalar_one_or_none()
                value = fact.model_dump(mode="json")
                if existing:
                    existing.value = value
                else:
                    ctx = ContextModel(
                        task_id=f"user_profile:{user_id}",
                        key=key,
                        value=value,
                    )
                    session.add(ctx)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to save fact to DB for user {user_id}: {e}")

    async def _load_facts_from_db(self, user_id: str) -> List[UserFact]:
        """Load facts from PostgreSQL."""
        facts: List[UserFact] = []
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.task_id == f"user_profile:{user_id}"
                    )
                )
                rows = result.scalars().all()
                for row in rows:
                    if row.value and isinstance(row.value, dict) and "fact_id" in row.value:
                        try:
                            facts.append(UserFact(**row.value))
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Failed to load facts from DB for user {user_id}: {e}")
        return facts


# Module-level singleton
user_memory = UserMemoryProfile()
