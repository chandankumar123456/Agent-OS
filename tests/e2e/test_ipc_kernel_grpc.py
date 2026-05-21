"""IPC contract test: Python gRPC client talks to the AgentKernel over UDS.

This test proves the IPC transport layer works end-to-end:
1. Boots the kernel in-process with a gRPC server on a temp UDS path.
2. Connects a grpcio client stub to that socket.
3. Exercises CreateTask, GetTask, ListTasks RPCs.
4. Cleans up on teardown.

Run with::

    pytest tests/e2e/test_ipc_kernel_grpc.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ["AGENTOS_RUNTIME_MODE"] = "grpc"
os.environ["RUNTIME_MODE"] = "grpc"
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def grpc_kernel_server(tmp_path):
    """Boot the kernel + gRPC server on a temp UDS and yield (socket_path, kernel)."""
    from core.desktop_native.kernel import AgentKernel
    from core.desktop_native.sqlite_store import sqlite_store
    from core.desktop_native.sqlite_tuning import sqlite_tuning
    from core.desktop_native.resource_monitor import resource_monitor
    from core.desktop_native.state_machine import TaskState
    from core.ipc.grpc_server import GRPCServer

    # Isolate DB
    db_path = str(tmp_path / "test.db")
    sqlite_store._db_path = db_path
    sqlite_store._connection = None

    await sqlite_store.initialize_schema()
    await sqlite_tuning.apply_optimizations()

    # Build a stub kernel (no LLM calls)
    class _StubKernel(AgentKernel):
        async def start(self):
            if self._running:
                return
            self._runtime = MagicMock()
            self._orchestrator = MagicMock()
            self._checkpointer = MagicMock()
            await resource_monitor.start()
            self._running = True
            for i in range(self.max_concurrent):
                worker = asyncio.create_task(
                    self._worker_loop(f"worker-{i}"),
                    name=f"kernel_worker_{i}",
                )
                self._worker_tasks.add(worker)
                worker.add_done_callback(self._worker_tasks.discard)

        async def _execute_task(self, task_id, query, config, user_id):
            from core.desktop_native.state_machine import local_task_state_machine, TaskState

            current = await local_task_state_machine.get_current_state(task_id)
            if current == TaskState.PENDING:
                try:
                    await local_task_state_machine.transition(
                        task_id, TaskState.PENDING, TaskState.PLANNING,
                        triggered_by="ipc-test",
                    )
                except ValueError:
                    pass
            try:
                await local_task_state_machine.transition(
                    task_id, TaskState.PLANNING, TaskState.EXECUTING,
                    triggered_by="ipc-test",
                )
            except ValueError:
                pass
            return {"echo": query}

    kernel = _StubKernel(max_concurrent_tasks=2, task_timeout_seconds=10)
    await kernel.start()

    socket_path = str(tmp_path / "ipc-test.sock")

    grpc_server = GRPCServer(kernel=kernel)
    grpc_server._host = f"unix:{socket_path}"
    grpc_server._port = 0
    await grpc_server.start()

    yield socket_path, kernel

    await grpc_server.stop(grace=2.0)
    await kernel.stop(timeout=3.0)

    # Clean up sqlite connection
    conn = getattr(sqlite_store, "_connection", None)
    if conn is not None:
        try:
            await conn.close()
        except Exception:
            pass
        sqlite_store._connection = None


async def test_create_task_via_grpc(grpc_kernel_server):
    """CreateTask RPC returns a valid task with a task ID."""
    import grpc
    from core.proto import runtime_pb2, runtime_pb2_grpc

    socket_path, _ = grpc_kernel_server
    target = f"unix:{socket_path}"

    async with grpc.aio.insecure_channel(target) as channel:
        stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        response = await stub.CreateTask(
            runtime_pb2.CreateTaskRequest(query="hello from IPC test")
        )
        assert response.success is True, f"CreateTask failed: {response.error}"
        assert response.task.id, "Expected non-empty task ID"
        assert response.task.query == "hello from IPC test"


async def test_get_task_via_grpc(grpc_kernel_server):
    """GetTask RPC retrieves a previously created task."""
    import grpc
    from core.proto import runtime_pb2, runtime_pb2_grpc

    socket_path, _ = grpc_kernel_server
    target = f"unix:{socket_path}"

    async with grpc.aio.insecure_channel(target) as channel:
        stub = runtime_pb2_grpc.RuntimeServiceStub(channel)

        # Create a task first
        create_resp = await stub.CreateTask(
            runtime_pb2.CreateTaskRequest(query="get-task test")
        )
        assert create_resp.success
        task_id = create_resp.task.id

        # Small delay for the kernel to begin processing
        await asyncio.sleep(0.2)

        # Now retrieve it
        get_resp = await stub.GetTask(
            runtime_pb2.GetTaskRequest(task_id=task_id)
        )
        assert get_resp.success is True, f"GetTask failed: {get_resp.error}"
        assert get_resp.task.id == task_id


async def test_list_tasks_via_grpc(grpc_kernel_server):
    """ListTasks RPC returns all tasks submitted so far."""
    import grpc
    from core.proto import runtime_pb2, runtime_pb2_grpc

    socket_path, _ = grpc_kernel_server
    target = f"unix:{socket_path}"

    async with grpc.aio.insecure_channel(target) as channel:
        stub = runtime_pb2_grpc.RuntimeServiceStub(channel)

        # Submit two tasks
        await stub.CreateTask(
            runtime_pb2.CreateTaskRequest(query="list test 1")
        )
        await stub.CreateTask(
            runtime_pb2.CreateTaskRequest(query="list test 2")
        )

        await asyncio.sleep(0.1)

        # List all
        list_resp = await stub.ListTasks(
            runtime_pb2.ListTasksRequest(limit=100)
        )
        assert list_resp.success is True
        assert list_resp.total_count >= 2, f"Expected >= 2 tasks, got {list_resp.total_count}"


async def test_health_check_via_grpc(grpc_kernel_server):
    """HealthCheck RPC returns healthy=True when kernel is running."""
    import grpc
    from core.proto import runtime_pb2, runtime_pb2_grpc

    socket_path, _ = grpc_kernel_server
    target = f"unix:{socket_path}"

    async with grpc.aio.insecure_channel(target) as channel:
        stub = runtime_pb2_grpc.RuntimeServiceStub(channel)
        resp = await stub.HealthCheck(runtime_pb2.HealthCheckRequest())
        assert resp.healthy is True
        assert resp.version == "0.2.0"
