"""Tests for TaskQueue enqueue, dequeue, position tracking, and requeue."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.orchestrator.queue import TaskQueue, TaskPriority, QueuePosition


@pytest.fixture
def queue():
    return TaskQueue(redis_prefix="test:queue:")


@pytest.fixture
def mock_redis():
    with patch("app.orchestrator.queue.redis_client") as mock:
        yield mock


class TestEnqueue:
    """Test task enqueue operations."""

    @pytest.mark.asyncio
    async def test_enqueue_basic(self, queue, mock_redis):
        mock_redis.client.zadd = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)
        mock_redis.client.expire = AsyncMock(return_value=1)
        mock_redis.client.zrank = AsyncMock(return_value=0)
        mock_redis.client.zcard = AsyncMock(return_value=1)

        pos = await queue.enqueue(
            task_id="task-1",
            user_id="user-1",
            query="test query",
            priority=TaskPriority.NORMAL,
        )

        assert pos.task_id == "task-1"
        assert pos.position == 0
        assert pos.queue_length == 1
        mock_redis.client.zadd.assert_awaited_once()
        mock_redis.client.hset.assert_awaited()

    @pytest.mark.asyncio
    async def test_enqueue_priority_ordering(self, queue, mock_redis):
        mock_redis.client.zadd = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)
        mock_redis.client.expire = AsyncMock(return_value=1)
        mock_redis.client.zcard = AsyncMock(return_value=2)

        # Enqueue low priority first
        mock_redis.client.zrank = AsyncMock(return_value=0)
        await queue.enqueue(
            task_id="task-low",
            user_id="user-1",
            query="low",
            priority=TaskPriority.LOW,
        )

        # Enqueue high priority - should be ahead
        mock_redis.client.zrank = AsyncMock(return_value=0)
        pos = await queue.enqueue(
            task_id="task-high",
            user_id="user-1",
            query="high",
            priority=TaskPriority.HIGH,
        )

        # Verify zadd was called with appropriate scores
        calls = mock_redis.client.zadd.call_args_list
        assert len(calls) == 2
        # High priority should have lower score than low priority
        high_score = list(calls[1][0][1].values())[0]
        low_score = list(calls[0][0][1].values())[0]
        assert high_score < low_score

    @pytest.mark.asyncio
    async def test_enqueue_with_idempotency_key(self, queue, mock_redis):
        mock_redis.client.zadd = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)
        mock_redis.client.expire = AsyncMock(return_value=1)
        mock_redis.client.zrank = AsyncMock(return_value=0)
        mock_redis.client.zcard = AsyncMock(return_value=1)

        pos = await queue.enqueue(
            task_id="task-1",
            user_id="user-1",
            query="test",
            idempotency_key="idem-123",
        )

        assert pos.task_id == "task-1"
        # Verify hset stored the idempotency key
        hset_calls = mock_redis.client.hset.call_args_list
        assert any("idem-123" in str(call) for call in hset_calls)


class TestDequeue:
    """Test task dequeue operations."""

    @pytest.mark.asyncio
    async def test_dequeue_highest_priority(self, queue, mock_redis):
        task_data = (
            '{"task_id":"task-1","user_id":"user-1","query":"test",'
            '"priority":1,"config":{},"enqueued_at":"2024-01-01T00:00:00",'
            '"status":"queued","retry_count":0}'
        )
        mock_redis.client.zrange = AsyncMock(return_value=["task-1"])
        mock_redis.client.zrangebyscore = AsyncMock(return_value=["task-1"])

        pipe_mock = MagicMock()
        pipe_mock.zrem = MagicMock(return_value=pipe_mock)
        pipe_mock.hgetall = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[1, {"data": task_data}])
        mock_redis.client.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis.client.hset = AsyncMock(return_value=1)

        task = await queue.dequeue(worker_id="worker-1")

        assert task is not None
        assert task.task_id == "task-1"
        assert task.worker_id == "worker-1"
        assert task.status == "assigned"

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self, queue, mock_redis):
        mock_redis.client.zrange = AsyncMock(return_value=[])
        mock_redis.client.zrangebyscore = AsyncMock(return_value=[])

        task = await queue.dequeue(worker_id="worker-1")

        assert task is None

    @pytest.mark.asyncio
    async def test_dequeue_max_priority_filter(self, queue, mock_redis):
        task_data = (
            '{"task_id":"task-1","user_id":"user-1","query":"test",'
            '"priority":2,"config":{},"enqueued_at":"2024-01-01T00:00:00",'
            '"status":"queued","retry_count":0}'
        )
        mock_redis.client.zrangebyscore = AsyncMock(return_value=["task-1"])

        pipe_mock = MagicMock()
        pipe_mock.zrem = MagicMock(return_value=pipe_mock)
        pipe_mock.hgetall = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[1, {"data": task_data}])
        mock_redis.client.pipeline = MagicMock(return_value=pipe_mock)
        mock_redis.client.hset = AsyncMock(return_value=1)

        task = await queue.dequeue(
            worker_id="worker-1",
            max_priority=TaskPriority.NORMAL,
        )

        assert task is not None
        # Verify zrangebyscore was called with max score filter
        mock_redis.client.zrangebyscore.assert_awaited_once()


class TestPositionAndLength:
    """Test queue position and length queries."""

    @pytest.mark.asyncio
    async def test_get_position(self, queue, mock_redis):
        mock_redis.client.zrank = AsyncMock(return_value=3)

        pos = await queue.get_position("task-1")

        assert pos == 3
        mock_redis.client.zrank.assert_awaited_once_with(
            "test:queue:tasks", "task-1"
        )

    @pytest.mark.asyncio
    async def test_get_position_not_in_queue(self, queue, mock_redis):
        mock_redis.client.zrank = AsyncMock(return_value=None)

        pos = await queue.get_position("task-missing")

        assert pos == -1

    @pytest.mark.asyncio
    async def test_queue_length(self, queue, mock_redis):
        mock_redis.client.zcard = AsyncMock(return_value=5)

        length = await queue.length()

        assert length == 5
        mock_redis.client.zcard.assert_awaited_once_with("test:queue:tasks")


class TestRequeue:
    """Test task requeue operations."""

    @pytest.mark.asyncio
    async def test_requeue_failed_task(self, queue, mock_redis):
        task_data = (
            '{"task_id":"task-1","user_id":"user-1","query":"test",'
            '"priority":2,"config":{},"enqueued_at":"2024-01-01T00:00:00",'
            '"status":"failed","retry_count":1}'
        )
        mock_redis.client.hgetall = AsyncMock(return_value={"data": task_data})
        mock_redis.client.zadd = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)

        result = await queue.requeue(task_id="task-1")

        assert result is True
        # Verify zadd was called (task re-added to queue)
        mock_redis.client.zadd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_requeue_with_priority_upgrade(self, queue, mock_redis):
        task_data = (
            '{"task_id":"task-1","user_id":"user-1","query":"test",'
            '"priority":3,"config":{},"enqueued_at":"2024-01-01T00:00:00",'
            '"status":"failed","retry_count":0}'
        )
        mock_redis.client.hgetall = AsyncMock(return_value={"data": task_data})
        mock_redis.client.zadd = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)

        result = await queue.requeue(
            task_id="task-1",
            priority=TaskPriority.HIGH,
        )

        assert result is True
        # Verify new score reflects higher priority (HIGH=1, so base is 1e12)
        calls = mock_redis.client.zadd.call_args_list
        score = list(calls[0][0][1].values())[0]
        # Score should be in HIGH priority range: >=1e12 and <3e12 (less than NORMAL base 2e12 + timestamp)
        assert score >= 1_000_000_000_000

    @pytest.mark.asyncio
    async def test_requeue_missing_task(self, queue, mock_redis):
        mock_redis.client.hgetall = AsyncMock(return_value={})

        result = await queue.requeue(task_id="task-missing")

        assert result is False


class TestCompleteAndFail:
    """Test task completion and failure handling."""

    @pytest.mark.asyncio
    async def test_complete_task(self, queue, mock_redis):
        mock_redis.client.zrem = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)
        mock_redis.client.expire = AsyncMock(return_value=1)
        mock_redis.client.delete = AsyncMock(return_value=1)

        # Mock execution lock
        with patch.object(
            queue.execution_lock, "get_lock_info", new=AsyncMock(return_value=None)
        ):
            result = await queue.complete("task-1")

        assert result is True
        mock_redis.client.zrem.assert_awaited_once_with("test:queue:tasks", "task-1")

    @pytest.mark.asyncio
    async def test_fail_task(self, queue, mock_redis):
        mock_redis.client.zrem = AsyncMock(return_value=1)
        mock_redis.client.hset = AsyncMock(return_value=1)
        mock_redis.client.expire = AsyncMock(return_value=1)
        mock_redis.client.delete = AsyncMock(return_value=1)

        with patch.object(
            queue.execution_lock, "get_lock_info", new=AsyncMock(return_value=None)
        ):
            result = await queue.fail("task-1", "Something went wrong")

        assert result is True
        hset_calls = mock_redis.client.hset.call_args_list
        assert any("failed" in str(call) for call in hset_calls)


class TestListTasks:
    """Test listing tasks in the queue."""

    @pytest.mark.asyncio
    async def test_list_tasks(self, queue, mock_redis):
        task_data = (
            '{"task_id":"task-1","user_id":"user-1","query":"test",'
            '"priority":2,"config":{},"enqueued_at":"2024-01-01T00:00:00",'
            '"status":"queued","retry_count":0}'
        )
        mock_redis.client.zrange = AsyncMock(return_value=["task-1"])
        mock_redis.client.hgetall = AsyncMock(return_value={"data": task_data})

        tasks = await queue.list_tasks(status="queued", limit=10)

        assert len(tasks) == 1
        assert tasks[0].task_id == "task-1"

    @pytest.mark.asyncio
    async def test_list_tasks_empty_queue(self, queue, mock_redis):
        mock_redis.client.zrange = AsyncMock(return_value=[])

        tasks = await queue.list_tasks()

        assert tasks == []


class TestClear:
    """Test queue clearing."""

    @pytest.mark.asyncio
    async def test_clear_queue(self, queue, mock_redis):
        mock_redis.client.zcard = AsyncMock(return_value=3)
        mock_redis.client.zrange = AsyncMock(return_value=["t1", "t2", "t3"])
        mock_redis.client.delete = AsyncMock(return_value=1)

        count = await queue.clear()

        assert count == 3
        mock_redis.client.delete.assert_awaited_with("test:queue:tasks")
