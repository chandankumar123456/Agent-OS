import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError

from app.langgraph.checkpointer import PostgresCheckpointSaver


class FakeAsyncpgOrig23505:
    pgcode = "23505"


class FakeAsyncpgOrigOther:
    pgcode = "40001"


@pytest.mark.asyncio
async def test_aput_writes_handles_unique_violation_via_pgcode():
    """FR1.2: IntegrityError with pgcode=23505 is caught and suppressed
    via savepoint isolation, preserving other writes in the batch."""
    mock_session_factory = MagicMock()
    saver = PostgresCheckpointSaver(session_factory=mock_session_factory)
    mock_session = AsyncMock()
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            err = IntegrityError("stmt", "params", Exception("dup"))
            err.orig = FakeAsyncpgOrig23505()
            raise err
        return MagicMock()

    mock_session.execute = fake_execute
    mock_session.commit = AsyncMock()
    # begin_nested() is a regular (non-async) method that returns an
    # AsyncSessionTransaction supporting the async context manager protocol.
    mock_savepoint = AsyncMock()
    mock_savepoint.__aenter__.return_value = mock_savepoint
    mock_savepoint.__aexit__.return_value = False
    mock_session.begin_nested = MagicMock(return_value=mock_savepoint)
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    await saver.aput_writes(
        config={"configurable": {"thread_id": "t1", "checkpoint_ns": ""}},
        writes=[("1", "channel", b"data"), ("2", "channel2", b"data2")],
        task_path="path",
        task_id="task1",
    )
    # First write raises IntegrityError(23505) → caught, savepoint rolls back,
    # loop continues. Second write succeeds. Both writes attempted → 2 calls.
    assert call_count == 2
    # session.rollback() must NOT be called — savepoint isolation is used instead
    mock_session.rollback.assert_not_called()
    # Outer commit must be called exactly once for the batch
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_aput_writes_re_raises_non_23505_integrity_error():
    """FR1.2: IntegrityError without pgcode=23505 is re-raised, not suppressed."""
    mock_session_factory = MagicMock()
    saver = PostgresCheckpointSaver(session_factory=mock_session_factory)
    mock_session = AsyncMock()

    async def fake_execute(stmt):
        err = IntegrityError("stmt", "params", Exception("serialization"))
        err.orig = FakeAsyncpgOrigOther()
        raise err

    mock_session.execute = fake_execute
    mock_session.commit = AsyncMock()
    mock_savepoint = AsyncMock()
    mock_savepoint.__aenter__.return_value = mock_savepoint
    mock_savepoint.__aexit__.return_value = False
    mock_session.begin_nested = MagicMock(return_value=mock_savepoint)
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    with pytest.raises(IntegrityError) as exc_info:
        await saver.aput_writes(
            config={"configurable": {"thread_id": "t1", "checkpoint_ns": ""}},
            writes=[("1", "channel", b"data")],
            task_path="path",
            task_id="task1",
        )

    exc = exc_info.value
    assert isinstance(exc, IntegrityError)
    assert exc.orig.pgcode == "40001"
    # session.rollback() must NOT be called — savepoint isolation is used
    mock_session.rollback.assert_not_called()
    # commit should NOT be called since the write was not suppressed
    mock_session.commit.assert_not_called()
