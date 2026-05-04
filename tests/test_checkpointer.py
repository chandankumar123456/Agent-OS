import pytest
from unittest.mock import AsyncMock, MagicMock

from app.langgraph.checkpointer import PostgresCheckpointSaver


@pytest.mark.asyncio
async def test_aput_writes_upsert_handles_conflicts():
    """With on_conflict_do_nothing, duplicate writes are handled at the DB
    level — no exception raised. All writes proceed, commit called once."""
    mock_session_factory = MagicMock()
    saver = PostgresCheckpointSaver(session_factory=mock_session_factory)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    await saver.aput_writes(
        config={"configurable": {"thread_id": "t1", "checkpoint_ns": ""}},
        writes=[("1", "channel", b"data"), ("2", "channel2", b"data2")],
        task_path="path",
        task_id="task1",
    )
    # All writes attempted — on_conflict_do_nothing handles duplicates silently
    assert mock_session.execute.await_count == 2
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_aput_writes_propagates_execute_error():
    """Any error during session.execute propagates — no special case for
    IntegrityError since on_conflict_do_nothing prevents those entirely."""
    mock_session_factory = MagicMock()
    saver = PostgresCheckpointSaver(session_factory=mock_session_factory)
    mock_session = AsyncMock()

    async def fake_execute(stmt):
        raise RuntimeError("DB connection lost")

    mock_session.execute = fake_execute
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    with pytest.raises(RuntimeError, match="DB connection lost"):
        await saver.aput_writes(
            config={"configurable": {"thread_id": "t1", "checkpoint_ns": ""}},
            writes=[("1", "channel", b"data")],
            task_path="path",
            task_id="task1",
        )
    # commit should NOT be called since the write errored
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_aput_writes_happy_path():
    """All writes succeed without exceptions."""
    mock_session_factory = MagicMock()
    saver = PostgresCheckpointSaver(session_factory=mock_session_factory)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    await saver.aput_writes(
        config={"configurable": {"thread_id": "t1", "checkpoint_ns": ""}},
        writes=[("1", "ch1", b"data1"), ("2", "ch2", b"data2")],
        task_path="path",
        task_id="task1",
    )
    assert mock_session.execute.await_count == 2
    assert mock_session.commit.await_count == 1
