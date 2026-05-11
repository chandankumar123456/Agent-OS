"""Artifact store for structured agent output storage.

Provides durable storage for agent outputs (files, images, data) with
metadata tracking, versioning, and namespace isolation per task.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .short_term import redis_client
from .long_term import db
from ..logs.logger import logger
from ..orchestrator.errors import AgentOSError, ErrorCode, ErrorType


class ArtifactRef(BaseModel):
    """Reference to a stored artifact."""
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    artifact_type: str = Field(..., description="Type: file, image, report, code, data")
    uri: str = Field(..., description="Storage URI (local path or S3 URL)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    content_hash: Optional[str] = None
    size_bytes: int = Field(default=0)
    created_at: Optional[datetime] = None
    version: int = Field(default=1)


class ArtifactStore:
    """Stores and retrieves agent artifacts with metadata.

    Uses filesystem for content storage (local dev) and PostgreSQL
    for metadata indexing. Redis caches recent artifact metadata.

    Usage:
        store = ArtifactStore(storage_dir="./artifacts")
        ref = await store.store_artifact(task_id, "report", content_bytes, {"title": "Q1 Report"})
        artifact = await store.retrieve_artifact(ref.artifact_id)
    """

    def __init__(
        self,
        storage_dir: str = "./artifacts",
        redis_prefix: str = "agentos:artifact:",
        max_artifact_size_mb: int = 50,
    ):
        self.storage_dir = Path(storage_dir)
        self.redis_prefix = redis_prefix
        self.max_artifact_size = max_artifact_size_mb * 1024 * 1024
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> None:
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create artifact storage dir: {e}")

    def _redis_key(self, artifact_id: str) -> str:
        return f"{self.redis_prefix}{artifact_id}"

    def _task_index_key(self, task_id: str) -> str:
        return f"{self.redis_prefix}index:{task_id}"

    def _artifact_path(self, artifact_id: str, artifact_type: str) -> Path:
        """Determine filesystem path for artifact content."""
        # Shard by first 2 chars of artifact_id for even distribution
        shard = artifact_id[:2]
        shard_dir = self.storage_dir / shard
        shard_dir.mkdir(parents=True, exist_ok=True)
        ext = self._type_to_extension(artifact_type)
        return shard_dir / f"{artifact_id}{ext}"

    def _type_to_extension(self, artifact_type: str) -> str:
        mapping = {
            "file": ".bin",
            "image": ".png",
            "report": ".md",
            "code": ".py",
            "data": ".json",
            "text": ".txt",
            "html": ".html",
        }
        return mapping.get(artifact_type, ".bin")

    async def store_artifact(
        self,
        task_id: str,
        artifact_type: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        artifact_id: Optional[str] = None,
    ) -> ArtifactRef:
        """Store an artifact and return its reference.

        Args:
            task_id: The originating task ID.
            artifact_type: Type of artifact (file, image, report, code, data).
            content: Binary content of the artifact.
            metadata: Optional metadata dict.
            artifact_id: Optional explicit artifact ID.

        Returns:
            ArtifactRef with URI and metadata.

        Raises:
            AgentOSError: If storage fails or size limit exceeded.
        """
        if len(content) > self.max_artifact_size:
            raise AgentOSError(
                message=f"Artifact size {len(content)} exceeds limit {self.max_artifact_size}",
                error_type=ErrorType.VALIDATION_ERROR,
                recoverable=False,
                code=ErrorCode.VALIDATION_ERROR,
                context={"task_id": task_id, "size": len(content)},
                http_status=413,
            )

        now = datetime.now(timezone.utc)
        artifact_id = artifact_id or str(uuid4())
        content_hash = hashlib.sha256(content).hexdigest()
        artifact_path = self._artifact_path(artifact_id, artifact_type)

        try:
            artifact_path.write_bytes(content)
        except Exception as e:
            logger.error(f"Failed to write artifact {artifact_id}: {e}")
            raise AgentOSError(
                message=f"Artifact storage failed: {e}",
                error_type=ErrorType.EXECUTION_ERROR,
                recoverable=True,
                code=ErrorCode.EXECUTION_ERROR,
                context={"task_id": task_id, "artifact_id": artifact_id},
            )

        ref = ArtifactRef(
            artifact_id=artifact_id,
            task_id=task_id,
            artifact_type=artifact_type,
            uri=str(artifact_path),
            metadata=metadata or {},
            content_hash=content_hash,
            size_bytes=len(content),
            created_at=now,
        )

        # Cache metadata in Redis
        redis_key = self._redis_key(artifact_id)
        try:
            await redis_client.set(redis_key, ref.model_dump(mode="json"), expire=86400)
        except Exception as e:
            logger.warning(f"Redis artifact cache failed for {artifact_id}: {e}")

        # Update task index in Redis
        try:
            idx_key = self._task_index_key(task_id)
            idx_data = await redis_client.get(idx_key) or {"artifact_ids": []}
            if artifact_id not in idx_data["artifact_ids"]:
                idx_data["artifact_ids"].append(artifact_id)
                await redis_client.set(idx_key, idx_data, expire=86400)
        except Exception as e:
            logger.warning(f"Redis task index update failed for {task_id}: {e}")

        # Persist metadata to PostgreSQL
        await self._save_metadata_to_db(ref)

        logger.debug(f"Stored artifact {artifact_id} for task {task_id}")
        return ref

    async def retrieve_artifact(self, artifact_id: str) -> Optional[ArtifactRef]:
        """Retrieve artifact metadata by ID.

        Args:
            artifact_id: The artifact identifier.

        Returns:
            ArtifactRef if found, None otherwise.
        """
        redis_key = self._redis_key(artifact_id)
        try:
            data = await redis_client.get(redis_key)
            if data:
                return ArtifactRef(**data)
        except Exception as e:
            logger.warning(f"Redis artifact retrieve failed for {artifact_id}: {e}")

        # Fallback to DB
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(ContextModel.key == f"artifact:{artifact_id}")
                )
                row = result.scalar_one_or_none()
                if row and row.value:
                    return ArtifactRef(**row.value)
        except Exception as e:
            logger.warning(f"DB artifact retrieve failed for {artifact_id}: {e}")

        return None

    async def read_artifact_content(self, artifact_id: str) -> Optional[bytes]:
        """Read the raw content of an artifact.

        Args:
            artifact_id: The artifact identifier.

        Returns:
            Content bytes if found, None otherwise.
        """
        ref = await self.retrieve_artifact(artifact_id)
        if not ref:
            return None
        try:
            path = Path(ref.uri)
            if path.exists():
                return path.read_bytes()
        except Exception as e:
            logger.error(f"Failed to read artifact content {artifact_id}: {e}")
        return None

    async def list_artifacts_by_task(self, task_id: str) -> List[ArtifactRef]:
        """List all artifacts for a task.

        Args:
            task_id: The task identifier.

        Returns:
            List of ArtifactRef objects.
        """
        artifact_ids: List[str] = []

        # Try Redis index first
        idx_key = self._task_index_key(task_id)
        try:
            idx_data = await redis_client.get(idx_key)
            if idx_data:
                artifact_ids = idx_data.get("artifact_ids", [])
        except Exception as e:
            logger.warning(f"Redis task index read failed for {task_id}: {e}")

        # Fallback to DB query
        if not artifact_ids:
            try:
                async with db.get_session() as session:
                    from sqlalchemy import select
                    from .models import ContextModel
                    result = await session.execute(
                        select(ContextModel).where(
                            ContextModel.task_id == f"artifact_task:{task_id}"
                        )
                    )
                    rows = result.scalars().all()
                    artifact_ids = [row.key.replace("artifact:", "") for row in rows if row.key]
            except Exception as e:
                logger.warning(f"DB artifact list failed for {task_id}: {e}")

        refs: List[ArtifactRef] = []
        for aid in artifact_ids:
            ref = await self.retrieve_artifact(aid)
            if ref:
                refs.append(ref)
        return refs

    async def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact.

        Args:
            artifact_id: The artifact identifier.

        Returns:
            True if deleted, False otherwise.
        """
        ref = await self.retrieve_artifact(artifact_id)
        if not ref:
            return False

        # Delete file
        try:
            path = Path(ref.uri)
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete artifact file {artifact_id}: {e}")

        # Delete Redis entries
        try:
            await redis_client.delete(self._redis_key(artifact_id))
            if ref.task_id:
                idx_key = self._task_index_key(ref.task_id)
                idx_data = await redis_client.get(idx_key)
                if idx_data and artifact_id in idx_data.get("artifact_ids", []):
                    idx_data["artifact_ids"].remove(artifact_id)
                    await redis_client.set(idx_key, idx_data, expire=86400)
        except Exception as e:
            logger.warning(f"Redis artifact delete failed for {artifact_id}: {e}")

        # Delete DB entry
        try:
            async with db.get_session() as session:
                from sqlalchemy import delete
                from .models import ContextModel
                await session.execute(
                    delete(ContextModel).where(ContextModel.key == f"artifact:{artifact_id}")
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"DB artifact delete failed for {artifact_id}: {e}")

        logger.debug(f"Deleted artifact {artifact_id}")
        return True

    async def update_metadata(
        self,
        artifact_id: str,
        metadata_updates: Dict[str, Any],
    ) -> Optional[ArtifactRef]:
        """Update artifact metadata.

        Args:
            artifact_id: The artifact identifier.
            metadata_updates: Metadata fields to update.

        Returns:
            Updated ArtifactRef if found, None otherwise.
        """
        ref = await self.retrieve_artifact(artifact_id)
        if not ref:
            return None

        ref.metadata.update(metadata_updates)
        await self._save_metadata_to_db(ref)

        # Update Redis cache
        try:
            await redis_client.set(
                self._redis_key(artifact_id),
                ref.model_dump(mode="json"),
                expire=86400,
            )
        except Exception as e:
            logger.warning(f"Redis metadata update failed for {artifact_id}: {e}")

        return ref

    async def _save_metadata_to_db(self, ref: ArtifactRef) -> None:
        """Persist artifact metadata to PostgreSQL."""
        try:
            async with db.get_session() as session:
                from sqlalchemy import select
                from .models import ContextModel
                result = await session.execute(
                    select(ContextModel).where(
                        ContextModel.key == f"artifact:{ref.artifact_id}"
                    )
                )
                existing = result.scalar_one_or_none()
                value = ref.model_dump(mode="json")
                if existing:
                    existing.value = value
                    existing.task_id = f"artifact_task:{ref.task_id}"
                else:
                    ctx = ContextModel(
                        task_id=f"artifact_task:{ref.task_id}",
                        key=f"artifact:{ref.artifact_id}",
                        value=value,
                    )
                    session.add(ctx)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to save artifact metadata to DB: {e}")


# Module-level singleton
artifact_store = ArtifactStore()
