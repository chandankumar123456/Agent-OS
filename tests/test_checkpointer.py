import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError

from app.langgraph.checkpointer import PostgresCheckpointSaver


class FakeAsyncpgOrig:
    pgcode = "23505"


@pytest.mark.asyncio
async def test_aput_writes_handles_unique_violation_via_pgcode():
    mock_session_factory = MagicMock()
    saver = PostgresCheckpointSaver(session_factory=mock_session_factory)
    mock_session = AsyncMock()
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            err = IntegrityError("stmt", "params", Exception("dup"))
            err.orig = FakeAsyncpgOrig()
            raise err
        return MagicMock()

    mock_session.execute = fake_execute
    mock_session.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = False

    await saver.aput_writes(
        config={"configurable": {"thread_id": "t1", "checkpoint_ns": ""}},
        writes=[("1", "channel", b"data")],
        task_path=["path"],
        task_id="task1",
    )
    # Single write causes one execute call; IntegrityError with pgcode 23505
    # is caught and suppressed, so the method completes without raising.
    assert call_count == 1
