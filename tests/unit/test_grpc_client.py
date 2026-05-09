#!/usr/bin/env python3
"""
Unit Tests for AgentOS gRPC Client Stubs
Tests RuntimeServiceClient, CheckpointServiceClient, WorkerServiceClient
with mocked gRPC channels.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from google.protobuf import empty_pb2

from app.proto.grpc_client import (
    GRPCClient,
    GRPCClientConfig,
    RuntimeServiceClient,
    CheckpointServiceClient,
    WorkerServiceClient,
)


class TestRuntimeServiceClient:
    """Unit tests for RuntimeServiceClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create a mock RuntimeServiceStub."""
        stub = MagicMock()
        stub.CreateTask = AsyncMock()
        stub.GetTask = AsyncMock()
        stub.CancelTask = AsyncMock()
        stub.ListTasks = AsyncMock()
        stub.HealthCheck = AsyncMock()
        stub.GetRuntimeStatus = AsyncMock()
        return stub

    @pytest.fixture
    def client(self, mock_stub):
        """Create a RuntimeServiceClient with mocked stub."""
        return RuntimeServiceClient(mock_stub)

    @pytest.mark.asyncio
    async def test_create_task_success(self, client, mock_stub):
        """Test creating a task successfully."""
        # Mock response
        mock_response = MagicMock()
        mock_response.task_id = "test-task-123"
        mock_response.success = True
        mock_stub.CreateTask.return_value = mock_response

        # Call method
        response = await client.create_task(
            query="Navigate to example.com",
            task_type=1,
            require_approval=False,
            timeout_seconds=300,
            parent_task_id="",
            config={"key": "value"}
        )

        # Verify
        assert response.task_id == "test-task-123"
        assert response.success is True
        mock_stub.CreateTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task_success(self, client, mock_stub):
        """Test getting a task by ID."""
        mock_response = MagicMock()
        mock_response.task_id = "test-task-123"
        mock_response.status = 1  # TASK_STATUS_COMPLETED
        mock_stub.GetTask.return_value = mock_response

        response = await client.get_task("test-task-123")

        assert response.task_id == "test-task-123"
        assert response.status == 1
        mock_stub.GetTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_task_success(self, client, mock_stub):
        """Test cancelling a task."""
        mock_response = MagicMock()
        mock_response.success = True
        mock_stub.CancelTask.return_value = mock_response

        response = await client.cancel_task("test-task-123", "User request")

        assert response.success is True
        mock_stub.CancelTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_success(self, client, mock_stub):
        """Test listing tasks with filters."""
        mock_response = MagicMock()
        mock_response.tasks = []
        mock_response.total_count = 0
        mock_stub.ListTasks.return_value = mock_response

        response = await client.list_tasks(
            filter_status=0,
            limit=100,
            offset=0,
            include_completed=True
        )

        assert response.total_count == 0
        mock_stub.ListTasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_stub):
        """Test health check endpoint."""
        mock_response = MagicMock()
        mock_response.healthy = True
        mock_response.version = "0.2.0"
        mock_stub.HealthCheck.return_value = mock_response

        response = await client.health_check()

        assert response.healthy is True
        assert response.version == "0.2.0"
        mock_stub.HealthCheck.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_runtime_status_success(self, client, mock_stub):
        """Test getting runtime status."""
        mock_response = MagicMock()
        mock_response.version = "0.2.0"
        mock_response.state = 1  # RUNTIME_STATE_READY
        mock_response.active_tasks = 5
        mock_stub.GetRuntimeStatus.return_value = mock_response

        response = await client.get_runtime_status(include_metrics=True)

        assert response.version == "0.2.0"
        assert response.state == 1
        assert response.active_tasks == 5
        mock_stub.GetRuntimeStatus.assert_called_once()


class TestCheckpointServiceClient:
    """Unit tests for CheckpointServiceClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create a mock CheckpointServiceStub."""
        stub = MagicMock()
        stub.SaveCheckpoint = AsyncMock()
        stub.GetCheckpoint = AsyncMock()
        stub.ListCheckpoints = AsyncMock()
        stub.GetLatestCheckpoint = AsyncMock()
        stub.CheckpointHealth = AsyncMock()
        return stub

    @pytest.fixture
    def client(self, mock_stub):
        """Create a CheckpointServiceClient with mocked stub."""
        return CheckpointServiceClient(mock_stub)

    @pytest.mark.asyncio
    async def test_save_checkpoint_success(self, client, mock_stub):
        """Test saving a checkpoint."""
        mock_response = MagicMock()
        mock_response.checkpoint_id = "checkpoint-123"
        mock_stub.SaveCheckpoint.return_value = mock_response

        response = await client.save_checkpoint(
            thread_id="thread-123",
            checkpoint_type=1,
            state_blob=b"state_data",
            channel_values=b"channel_data",
            pending_sends=b"pending_data",
            parent_ids=["parent-1"],
            metadata="test metadata",
            task_id="task-123"
        )

        assert response.checkpoint_id == "checkpoint-123"
        mock_stub.SaveCheckpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_checkpoint_success(self, client, mock_stub):
        """Test getting a checkpoint by ID."""
        mock_response = MagicMock()
        mock_response.checkpoint_id = "checkpoint-123"
        mock_response.thread_id = "thread-123"
        mock_stub.GetCheckpoint.return_value = mock_response

        response = await client.get_checkpoint("checkpoint-123")

        assert response.checkpoint_id == "checkpoint-123"
        assert response.thread_id == "thread-123"
        mock_stub.GetCheckpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_checkpoints_success(self, client, mock_stub):
        """Test listing checkpoints for a thread."""
        mock_response = MagicMock()
        mock_response.checkpoints = []
        mock_response.count = 0
        mock_stub.ListCheckpoints.return_value = mock_response

        response = await client.list_checkpoints(
            thread_id="thread-123",
            limit=100,
            offset=0,
            include_metadata=True
        )

        assert response.count == 0
        mock_stub.ListCheckpoints.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_checkpoint_success(self, client, mock_stub):
        """Test getting the latest checkpoint for a thread."""
        mock_response = MagicMock()
        mock_response.checkpoint_id = "checkpoint-latest"
        mock_stub.GetLatestCheckpoint.return_value = mock_response

        response = await client.get_latest_checkpoint("thread-123", include_metadata=True)

        assert response.checkpoint_id == "checkpoint-latest"
        mock_stub.GetLatestCheckpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_stub):
        """Test checkpoint service health check."""
        mock_response = MagicMock()
        mock_response.healthy = True
        mock_stub.CheckpointHealth.return_value = mock_response

        response = await client.health_check()

        assert response.healthy is True
        mock_stub.CheckpointHealth.assert_called_once()


class TestWorkerServiceClient:
    """Unit tests for WorkerServiceClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create a mock WorkerExecutorStub."""
        stub = MagicMock()
        stub.ExecuteTask = AsyncMock()
        stub.HealthCheck = AsyncMock()
        return stub

    @pytest.fixture
    def client(self, mock_stub):
        """Create a WorkerServiceClient with mocked stub."""
        return WorkerServiceClient(mock_stub)

    @pytest.mark.asyncio
    async def test_execute_task_success(self, client, mock_stub):
        """Test executing a task."""
        mock_response = MagicMock()
        mock_response.task_id = "task-123"
        mock_response.success = True
        mock_response.result = '{"status": "completed"}'
        mock_stub.ExecuteTask.return_value = mock_response

        response = await client.execute_task(
            task_id="task-123",
            task_type="mcp_tool_call",
            payload='{"action": "click"}',
            timeout_seconds=300,
            metadata={"worker": "worker-1"}
        )

        assert response.task_id == "task-123"
        assert response.success is True
        mock_stub.ExecuteTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, client, mock_stub):
        """Test worker service health check."""
        mock_response = MagicMock()
        mock_response.healthy = True
        mock_response.status = "ok"
        mock_stub.HealthCheck.return_value = mock_response

        response = await client.health_check(worker_id="worker-1")

        assert response.healthy is True
        assert response.status == "ok"
        mock_stub.HealthCheck.assert_called_once()


class TestGRPCClient:
    """Unit tests for GRPCClient wrapper."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful gRPC connection."""
        config = GRPCClientConfig(host="localhost", port=50051)

        # Mock the async channel and stubs
        mock_channel = AsyncMock()
        mock_channel.close = AsyncMock()
        
        # Create separate stubs for each service
        runtime_stub = MagicMock()
        runtime_stub.CreateTask = AsyncMock()
        runtime_stub.GetTask = AsyncMock()
        runtime_stub.CancelTask = AsyncMock()
        runtime_stub.ListTasks = AsyncMock()
        runtime_stub.HealthCheck = AsyncMock()
        runtime_stub.GetRuntimeStatus = AsyncMock()
        
        checkpoint_stub = MagicMock()
        checkpoint_stub.SaveCheckpoint = AsyncMock()
        checkpoint_stub.GetCheckpoint = AsyncMock()
        checkpoint_stub.ListCheckpoints = AsyncMock()
        checkpoint_stub.GetLatestCheckpoint = AsyncMock()
        checkpoint_stub.CheckpointHealth = AsyncMock()
        
        worker_stub = MagicMock()
        worker_stub.ExecuteTask = AsyncMock()
        worker_stub.HealthCheck = AsyncMock()

        # Create mock modules for the gRPC imports
        mock_runtime_grpc = MagicMock()
        mock_runtime_grpc.RuntimeServiceStub.return_value = runtime_stub
        
        mock_checkpoint_grpc = MagicMock()
        mock_checkpoint_grpc.CheckpointServiceStub.return_value = checkpoint_stub
        
        mock_worker_grpc = MagicMock()
        mock_worker_grpc.WorkerExecutorStub.return_value = worker_stub

        with patch('grpc.aio.insecure_channel', return_value=mock_channel) as mock_grpc_channel:
            with patch('app.proto.grpc_client.runtime_pb2_grpc', mock_runtime_grpc), \
                 patch('app.proto.grpc_client.checkpoint_pb2_grpc', mock_checkpoint_grpc), \
                 patch('app.proto.grpc_client.worker_pb2_grpc', mock_worker_grpc):

                client = GRPCClient(config)
                await client.connect()

                assert client.is_connected is True
                mock_grpc_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Test connection failure handling."""
        config = GRPCClientConfig(host="invalid-host", port=9999)

        with patch('grpc.aio.insecure_channel') as mock_grpc_channel:
            mock_grpc_channel.side_effect = Exception("Connection refused")

            client = GRPCClient(config)

            with pytest.raises(Exception):
                await client.connect()

            assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_close_success(self):
        """Test successful gRPC connection close."""
        config = GRPCClientConfig()

        # Mock the async channel
        mock_channel = AsyncMock()
        mock_channel.close = AsyncMock()
        
        with patch('app.proto.grpc_client.grpc.aio.insecure_channel', return_value=mock_channel) as mock_grpc_channel:
            mock_runtime_stub = MagicMock()
            mock_runtime_stub.CreateTask = AsyncMock()
            mock_runtime_stub.GetTask = AsyncMock()
            mock_runtime_stub.CancelTask = AsyncMock()
            mock_runtime_stub.ListTasks = AsyncMock()
            mock_runtime_stub.HealthCheck = AsyncMock()
            mock_runtime_stub.GetRuntimeStatus = AsyncMock()
            mock_runtime_stub.SaveCheckpoint = AsyncMock()
            mock_runtime_stub.GetCheckpoint = AsyncMock()
            mock_runtime_stub.ListCheckpoints = AsyncMock()
            mock_runtime_stub.GetLatestCheckpoint = AsyncMock()
            mock_runtime_stub.CheckpointHealth = AsyncMock()
            mock_runtime_stub.ExecuteTask = AsyncMock()
            mock_runtime_stub.HealthCheck = AsyncMock()

            with patch('app.proto.grpc_client.runtime_pb2_grpc') as mock_runtime_grpc, \
                 patch('app.proto.grpc_client.checkpoint_pb2_grpc') as mock_checkpoint_grpc, \
                 patch('app.proto.grpc_client.worker_pb2_grpc') as mock_worker_grpc:

                mock_runtime_grpc.RuntimeServiceStub.return_value = mock_runtime_stub
                mock_checkpoint_grpc.CheckpointServiceStub.return_value = mock_runtime_stub
                mock_worker_grpc.WorkerExecutorStub.return_value = mock_runtime_stub

                client = GRPCClient(config)
                await client.connect()
                await client.close()

                assert client.is_connected is False
                mock_grpc_channel.assert_called_once()
                mock_channel.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager entry/exit."""
        config = GRPCClientConfig()

        with patch('grpc.aio.insecure_channel') as mock_channel:
            mock_channel.close = AsyncMock()
            mock_channel.return_value = mock_channel

            with patch('app.proto.grpc_client.runtime_pb2_grpc') as mock_runtime_grpc, \
                 patch('app.proto.grpc_client.checkpoint_pb2_grpc') as mock_checkpoint_grpc, \
                 patch('app.proto.grpc_client.worker_pb2_grpc') as mock_worker_grpc:

                mock_runtime_grpc.RuntimeServiceStub.return_value = MagicMock()
                mock_checkpoint_grpc.CheckpointServiceStub.return_value = MagicMock()
                mock_worker_grpc.WorkerExecutorStub.return_value = MagicMock()

                async with GRPCClient(config) as client:
                    assert client.is_connected is True

                assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_health_check_all_services(self):
        """Test health check across all services."""
        config = GRPCClientConfig()

        with patch('grpc.aio.insecure_channel') as mock_channel:
            mock_channel.close = AsyncMock()
            mock_channel.return_value = mock_channel

            with patch('app.proto.grpc_client.runtime_pb2_grpc') as mock_runtime_grpc, \
                 patch('app.proto.grpc_client.checkpoint_pb2_grpc') as mock_checkpoint_grpc, \
                 patch('app.proto.grpc_client.worker_pb2_grpc') as mock_worker_grpc:

                # Create mock stubs
                runtime_stub = MagicMock()
                checkpoint_stub = MagicMock()
                worker_stub = MagicMock()

                # Set up health check responses
                runtime_stub.HealthCheck = AsyncMock(return_value=MagicMock(healthy=True))
                checkpoint_stub.CheckpointHealth = AsyncMock(return_value=MagicMock(healthy=True))
                worker_stub.HealthCheck = AsyncMock(return_value=MagicMock(healthy=True))

                mock_runtime_grpc.RuntimeServiceStub.return_value = runtime_stub
                mock_checkpoint_grpc.CheckpointServiceStub.return_value = checkpoint_stub
                mock_worker_grpc.WorkerExecutorStub.return_value = worker_stub

                client = GRPCClient(config)
                await client.connect()

                # Test health check
                is_healthy = await client.health_check()
                assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure handling."""
        config = GRPCClientConfig()

        with patch('grpc.aio.insecure_channel') as mock_channel:
            mock_channel.close = AsyncMock()
            mock_channel.return_value = mock_channel

            with patch('app.proto.grpc_client.runtime_pb2_grpc') as mock_runtime_grpc, \
                 patch('app.proto.grpc_client.checkpoint_pb2_grpc') as mock_checkpoint_grpc, \
                 patch('app.proto.grpc_client.worker_pb2_grpc') as mock_worker_grpc:

                runtime_stub = MagicMock()
                runtime_stub.HealthCheck = AsyncMock(side_effect=Exception("Service unavailable"))

                mock_runtime_grpc.RuntimeServiceStub.return_value = runtime_stub
                mock_checkpoint_grpc.CheckpointServiceStub.return_value = MagicMock()
                mock_worker_grpc.WorkerExecutorStub.return_value = MagicMock()

                client = GRPCClient(config)
                await client.connect()

                is_healthy = await client.health_check()
                assert is_healthy is False

    def test_properties(self):
        """Test client property accessors."""
        config = GRPCClientConfig()

        with patch('grpc.aio.insecure_channel') as mock_channel, \
             patch('app.proto.grpc_client.runtime_pb2_grpc'), \
             patch('app.proto.grpc_client.checkpoint_pb2_grpc'), \
             patch('app.proto.grpc_client.worker_pb2_grpc'):

            mock_channel.return_value = mock_channel

            client = GRPCClient(config)

            # Check properties are accessible
            assert hasattr(client, 'runtime')
            assert hasattr(client, 'checkpoint')
            assert hasattr(client, 'worker')
            assert hasattr(client, 'is_connected')
