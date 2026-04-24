"""PostgreSQL checkpointer for LangGraph state persistence."""
import json
from typing import Any, AsyncIterator, Dict, List, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from sqlalchemy import select, delete

from ..memory.models import CheckpointModel
from ..memory.long_term import db
from ..logs.logger import logger


_serde = JsonPlusSerializer()


def _encode(data: Any) -> str:
    return json.dumps(_serde.dumps_typed(data))


def _decode(text: str) -> Any:
    return _serde.loads_typed(json.loads(text))


class PostgresCheckpointSaver(BaseCheckpointSaver):
    """Async PostgreSQL-backed checkpoint saver for LangGraph.

    Persists agent state to the `checkpoints` table so graphs can be resumed
    across process restarts.
    """

    def __init__(self):
        super().__init__()

    async def aput(
        self,
        config: Dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = checkpoint.get("parent_config", {}).get("configurable", {}).get("checkpoint_id") if checkpoint.get("parent_config") else None

        async with db.get_session() as session:
            existing = await session.execute(
                select(CheckpointModel).where(
                    CheckpointModel.thread_id == thread_id,
                    CheckpointModel.checkpoint_ns == checkpoint_ns,
                    CheckpointModel.checkpoint_id == checkpoint_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.checkpoint = _encode(checkpoint)
                row.checkpoint_metadata = _encode(metadata)
                row.parent_checkpoint_id = parent_checkpoint_id
            else:
                row = CheckpointModel(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=parent_checkpoint_id,
                    checkpoint=_encode(checkpoint),
                    checkpoint_metadata=_encode(metadata),
                )
                session.add(row)
            await session.commit()

        logger.debug(f"Checkpoint saved: {thread_id}/{checkpoint_ns}/{checkpoint_id}")
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aget_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        async with db.get_session() as session:
            if checkpoint_id:
                result = await session.execute(
                    select(CheckpointModel).where(
                        CheckpointModel.thread_id == thread_id,
                        CheckpointModel.checkpoint_ns == checkpoint_ns,
                        CheckpointModel.checkpoint_id == checkpoint_id,
                    )
                )
            else:
                result = await session.execute(
                    select(CheckpointModel)
                    .where(
                        CheckpointModel.thread_id == thread_id,
                        CheckpointModel.checkpoint_ns == checkpoint_ns,
                    )
                    .order_by(CheckpointModel.created_at.desc())
                    .limit(1)
                )
            row = result.scalar_one_or_none()
            if not row:
                return None

            checkpoint = _decode(row.checkpoint)
            metadata = _decode(row.checkpoint_metadata) if row.checkpoint_metadata else {}

            parent_config = None
            if row.parent_checkpoint_id:
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": row.parent_checkpoint_id,
                    }
                }

            return CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": row.checkpoint_id,
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
                pending_writes=None,
                pending_sends=None,
            )

    async def alist(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"] if config else None
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "") if config else ""

        async with db.get_session() as session:
            query = select(CheckpointModel).where(CheckpointModel.checkpoint_ns == checkpoint_ns)
            if thread_id:
                query = query.where(CheckpointModel.thread_id == thread_id)
            if before:
                before_id = before["configurable"].get("checkpoint_id")
                if before_id:
                    query = query.where(CheckpointModel.checkpoint_id < before_id)
            query = query.order_by(CheckpointModel.created_at.desc())
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            rows = result.scalars().all()

            for row in rows:
                checkpoint = _decode(row.checkpoint)
                metadata = _decode(row.checkpoint_metadata) if row.checkpoint_metadata else {}
                parent_config = None
                if row.parent_checkpoint_id:
                    parent_config = {
                        "configurable": {
                            "thread_id": row.thread_id,
                            "checkpoint_ns": row.checkpoint_ns,
                            "checkpoint_id": row.parent_checkpoint_id,
                        }
                    }
                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": row.thread_id,
                            "checkpoint_ns": row.checkpoint_ns,
                            "checkpoint_id": row.checkpoint_id,
                        }
                    },
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=parent_config,
                    pending_writes=None,
                    pending_sends=None,
                )

    async def adelete(self, config: Dict[str, Any]) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        async with db.get_session() as session:
            await session.execute(
                delete(CheckpointModel).where(
                    CheckpointModel.thread_id == thread_id,
                    CheckpointModel.checkpoint_ns == checkpoint_ns,
                )
            )
            await session.commit()
