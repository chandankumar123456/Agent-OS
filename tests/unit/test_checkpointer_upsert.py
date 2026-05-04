"""Tests for PostgresCheckpointSaver upsert behavior on duplicate writes."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.langgraph.checkpointer import PostgresCheckpointSaver


@pytest.mark.asyncio
async def test_aput_writes_uses_upsert_no_exception():
    """Duplicate checkpoint writes must not raise.

    Verifies that aput_writes uses on_conflict_do_nothing with the
    correct constraint name, so duplicate task writes are silently ignored.
    """
    saver = PostgresCheckpointSaver()
    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    mock_model = MagicMock()
    mock_model.__tablename__ = "checkpoint_writes"

    # Inject mock session via _session_factory
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_session
    mock_ctx.__aexit__.return_value = None
    saver._session_factory = lambda: mock_ctx

    config = {
        "configurable": {
            "thread_id": "t1",
            "checkpoint_ns": "ns1",
            "checkpoint_id": "cp1",
        }
    }
    writes = [("task1", "channel1", "value1")]

    with patch.object(saver, "_get_checkpoint_model", return_value=mock_model):
        with patch("sqlalchemy.dialects.postgresql.insert") as mock_pg_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_nothing.return_value = mock_stmt
            mock_pg_insert.return_value.values.return_value = mock_stmt

            await saver.aput_writes(
                config=config,
                writes=writes,
                task_id="task1",
                task_path="path1",
            )

            mock_stmt.on_conflict_do_nothing.assert_called_once_with(
                constraint="uq_checkpoint_write"
            )
            mock_session.execute.assert_called_once_with(mock_stmt)
