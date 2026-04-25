import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.memory.task_memory import TaskMemory, task_memory
from app.memory.session_memory import SessionMemory, session_memory
from app.memory.workflow_memory import WorkflowMemory, workflow_memory
from app.memory.user_memory import UserMemory, user_memory


@pytest.mark.asyncio
async def test_task_memory_set_get():
    mock_redis = AsyncMock()
    with patch("app.memory.task_memory.redis_client", mock_redis):
        mem = TaskMemory()
        mock_redis.get.return_value = {"foo": "bar"}
        result = await mem.get("t1")
        mock_redis.get.assert_awaited_once_with("agentos:memory:task:t1")
        assert result == {"foo": "bar"}

        mock_redis.set.return_value = True
        ok = await mem.set("t1", {"foo": "baz"}, expire=1800)
        mock_redis.set.assert_awaited_once_with("agentos:memory:task:t1", {"foo": "baz"}, 1800)
        assert ok is True


@pytest.mark.asyncio
async def test_task_memory_update_progress():
    mock_redis = AsyncMock()
    with patch("app.memory.task_memory.redis_client", mock_redis):
        mem = TaskMemory()
        mock_redis.get.return_value = {"existing": "data"}
        mock_redis.set.return_value = True
        ok = await mem.update_progress("t1", 2, {"status": "running"}, expire=1800)
        mock_redis.get.assert_awaited_once_with("agentos:memory:task:t1")
        expected = {
            "existing": "data",
            "progress": {
                "2": {"status": "running"},
            },
        }
        mock_redis.set.assert_awaited_once_with("agentos:memory:task:t1", expected, 1800)
        assert ok is True


@pytest.mark.asyncio
async def test_task_memory_clear():
    mock_redis = AsyncMock()
    with patch("app.memory.task_memory.redis_client", mock_redis):
        mem = TaskMemory()
        mock_redis.delete.return_value = True
        ok = await mem.clear("t1")
        mock_redis.delete.assert_awaited_once_with("agentos:memory:task:t1")
        assert ok is True


@pytest.mark.asyncio
async def test_session_memory_browser_session_roundtrip():
    mock_redis = AsyncMock()
    with patch("app.memory.session_memory.redis_client", mock_redis):
        mem = SessionMemory()
        mock_redis.set.return_value = True
        ok = await mem.set_browser_session("t1", {"cookies": ["a"]}, expire=3600)
        mock_redis.set.assert_awaited_once_with(
            "agentos:memory:session:t1:browser",
            {"cookies": ["a"]},
            3600,
        )
        assert ok is True

        mock_redis.get.return_value = {"cookies": ["a"]}
        result = await mem.get_browser_session("t1")
        mock_redis.get.assert_awaited_with("agentos:memory:session:t1:browser")
        assert result == {"cookies": ["a"]}


@pytest.mark.asyncio
async def test_session_memory_active_envs_roundtrip():
    mock_redis = AsyncMock()
    with patch("app.memory.session_memory.redis_client", mock_redis):
        mem = SessionMemory()
        mock_redis.set.return_value = True
        ok = await mem.set_active_envs("t1", {"env": "prod"}, expire=3600)
        mock_redis.set.assert_awaited_once_with(
            "agentos:memory:session:t1:envs",
            {"env": "prod"},
            3600,
        )
        assert ok is True

        mock_redis.get.return_value = {"env": "prod"}
        result = await mem.get_active_envs("t1")
        mock_redis.get.assert_awaited_with("agentos:memory:session:t1:envs")
        assert result == {"env": "prod"}


@pytest.mark.asyncio
async def test_workflow_memory_get_state():
    mock_repo = AsyncMock()
    mock_node_repo = AsyncMock()
    with patch("app.memory.workflow_memory.workflow_repo", mock_repo), patch(
        "app.memory.workflow_memory.workflow_node_repo", mock_node_repo
    ):
        mem = WorkflowMemory()
        wf = MagicMock()
        wf.id = "wf1"
        wf.task_id = "t1"
        wf.status = "pending"
        wf.definition = {"nodes": []}
        mock_repo.get_by_id.return_value = wf

        state = await mem.get_state("wf1")
        mock_repo.get_by_id.assert_awaited_once_with("wf1")
        assert state == {
            "id": "wf1",
            "task_id": "t1",
            "status": "pending",
            "definition": {"nodes": []},
        }


@pytest.mark.asyncio
async def test_workflow_memory_save_state():
    mock_repo = AsyncMock()
    mock_node_repo = AsyncMock()
    with patch("app.memory.workflow_memory.workflow_repo", mock_repo), patch(
        "app.memory.workflow_memory.workflow_node_repo", mock_node_repo
    ):
        mem = WorkflowMemory()
        wf = MagicMock()
        wf.id = "wf1"
        wf.task_id = "t1"
        wf.status = "running"
        wf.definition = {"nodes": [1]}
        mock_repo.update.return_value = wf

        result = await mem.save_state("wf1", {"nodes": [1]})
        mock_repo.update.assert_awaited_once_with("wf1", definition={"nodes": [1]})
        assert result == {
            "id": "wf1",
            "task_id": "t1",
            "status": "running",
            "definition": {"nodes": [1]},
        }


@pytest.mark.asyncio
async def test_workflow_memory_get_node_status():
    mock_repo = AsyncMock()
    mock_node_repo = AsyncMock()
    with patch("app.memory.workflow_memory.workflow_repo", mock_repo), patch(
        "app.memory.workflow_memory.workflow_node_repo", mock_node_repo
    ):
        mem = WorkflowMemory()
        node = MagicMock()
        node.workflow_id = "wf1"
        node.status = "pending"
        mock_node_repo.get_by_id.return_value = node

        status = await mem.get_node_status("wf1", "n1")
        mock_node_repo.get_by_id.assert_awaited_once_with("n1")
        assert status == "pending"


@pytest.mark.asyncio
async def test_workflow_memory_get_node_status_wrong_workflow():
    mock_repo = AsyncMock()
    mock_node_repo = AsyncMock()
    with patch("app.memory.workflow_memory.workflow_repo", mock_repo), patch(
        "app.memory.workflow_memory.workflow_node_repo", mock_node_repo
    ):
        mem = WorkflowMemory()
        node = MagicMock()
        node.workflow_id = "wf2"
        node.status = "pending"
        mock_node_repo.get_by_id.return_value = node

        status = await mem.get_node_status("wf1", "n1")
        assert status is None


@pytest.mark.asyncio
async def test_workflow_memory_set_node_status():
    mock_repo = AsyncMock()
    mock_node_repo = AsyncMock()
    with patch("app.memory.workflow_memory.workflow_repo", mock_repo), patch(
        "app.memory.workflow_memory.workflow_node_repo", mock_node_repo
    ):
        mem = WorkflowMemory()
        node = MagicMock()
        node.id = "n1"
        node.workflow_id = "wf1"
        node.status = "completed"
        mock_node_repo.update.return_value = node

        result = await mem.set_node_status("wf1", "n1", "completed")
        mock_node_repo.update.assert_awaited_once_with("n1", status="completed")
        assert result == {
            "id": "n1",
            "workflow_id": "wf1",
            "status": "completed",
        }


@pytest.mark.asyncio
async def test_user_memory_preferences_roundtrip():
    mock_redis = AsyncMock()
    mock_config = AsyncMock()
    with patch("app.memory.user_memory.redis_client", mock_redis), patch(
        "app.memory.user_memory.config_repo", mock_config
    ):
        mem = UserMemory()
        mock_redis.get.return_value = None
        mock_config.get.return_value = None

        mock_redis.set.return_value = True
        mock_config.upsert.return_value = MagicMock()

        ok = await mem.set_preference("u1", "theme", "dark")
        assert ok is True
        mock_config.upsert.assert_awaited_once_with(
            "user_prefs_u1",
            {"theme": "dark"},
        )
        mock_redis.set.assert_awaited_once_with(
            "agentos:memory:user:u1:prefs",
            {"theme": "dark"},
            expire=3600,
        )

        # Simulate cache hit on get_preferences
        mock_redis.get.return_value = {"theme": "dark"}
        prefs = await mem.get_preferences("u1")
        mock_redis.get.assert_awaited_with("agentos:memory:user:u1:prefs")
        assert prefs == {"theme": "dark"}
