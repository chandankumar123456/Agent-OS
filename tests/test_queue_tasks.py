import sys
import pytest
from unittest.mock import patch, MagicMock


class TestCeleryWorkerEventLoop:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_worker_init_sets_proactor_policy_on_windows(self):
        """On Windows, Celery worker must use ProactorEventLoop for subprocess support."""
        from core.queue.tasks import on_worker_process_init

        with patch("asyncio.set_event_loop_policy") as mock_set_policy:
            with patch("asyncio.get_running_loop", side_effect=RuntimeError):
                with patch("asyncio.new_event_loop") as mock_new_loop:
                    mock_loop = MagicMock()
                    mock_new_loop.return_value = mock_loop

                    # Mock DB/Redis connections and runtime (imports are inside func)
                    with patch("core.memory.long_term.db"):
                        with patch("core.memory.short_term.redis_client"):
                            with patch("core.memory.redis_pubsub.redis_pubsub_client"):
                                with patch("core.queue.tasks._ensure_runtime_initialized"):
                                    with patch("core.tools.builtin.register_builtin_tools"):
                                        with patch("core.mcp.client_manager.mcp_client_manager"):
                                            on_worker_process_init()

                    # Assert ProactorEventLoopPolicy was set
                    from asyncio import WindowsProactorEventLoopPolicy
                    mock_set_policy.assert_called_once()
                    args, _ = mock_set_policy.call_args
                    assert isinstance(args[0], WindowsProactorEventLoopPolicy)
