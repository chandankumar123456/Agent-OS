"""Unit tests for gRPC client wrapper.

Tests the gRPC client implementation for AgentOS runtime supervisor communication.
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.proto.grpc_client import (
    GRPCClient,
    GRPCClientConfig,
    RuntimeServiceClient,
    CheckpointServiceClient,
    WorkerServiceClient,
)


class TestGRPCClientConfig:
    """Tests for GRPCClientConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GRPCClientConfig()
        assert config.host == "localhost"
        assert config.port == 50051
        assert config.max_send_message_length == 50 * 1024 * 1024
        assert config.max_receive_message_length == 50 * 1024 * 1024
        assert config.connection_timeout == 5.0
        assert config.keepalive_timeout == 60

    def test_custom_config(self):
        """Test custom configuration values."""
        config = GRPCClientConfig(
            host="127.0.0.1",
            port=50052,
            max_send_message_length=100 * 1024 * 1024,
            max_receive_message_length=100 * 1024 * 1024,
            connection_timeout=10.0,
            keepalive_timeout=120,
        )
        assert config.host == "127.0.0.1"
        assert config.port == 50052
        assert config.max_send_message_length == 100 * 1024 * 1024
        assert config.max_receive_message_length == 100 * 1024 * 1024
        assert config.connection_timeout == 10.0
        assert config.keepalive_timeout == 120


class TestRuntimeServiceClient:
    """Tests for RuntimeServiceClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create mock RuntimeServiceStub."""
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
        """Create RuntimeServiceClient with mock stub."""
        return RuntimeServiceClient(mock_stub)

    @pytest.mark.asyncio
    async def test_create_task_default(self, client, mock_stub):
        """Test create_task with default parameters."""
        mock_response = MagicMock()
        mock_response.task_id = str(uuid4())
        mock_stub.CreateTask.return_value = mock_response

        response = await client.create_task(query="test query")

        assert response == mock_response
        mock_stub.CreateTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_custom(self, client, mock_stub):
        """Test create_task with custom parameters."""
        mock_response = MagicMock()
        mock_stub.CreateTask.return_value = mock_response

        config = {"key": "value"}
        response = await client.create_task(
            query="test query",
            task_type=2,  # TASK_TYPE_COMPLEX
            require_approval=True,
            timeout_seconds=600,
            parent_task_id=str(uuid4()),
            config=config,
        )

        assert response == mock_response
        mock_stub.CreateTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task(self, client, mock_stub):
        """Test get_task."""
        mock_response = MagicMock()
        mock_stub.GetTask.return_value = mock_response

        task_id = str(uuid4())
        response = await client.get_task(task_id)

        assert response == mock_response
        mock_stub.GetTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_task(self, client, mock_stub):
        """Test cancel_task."""
        mock_response = MagicMock()
        mock_stub.CancelTask.return_value = mock_response

        task_id = str(uuid4())
        reason = "test reason"
        response = await client.cancel_task(task_id, reason)

        assert response == mock_response
        mock_stub.CancelTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_default(self, client, mock_stub):
        """Test list_tasks with default parameters."""
        mock_response = MagicMock()
        mock_stub.ListTasks.return_value = mock_response

        response = await client.list_tasks()

        assert response == mock_response
        mock_stub.ListTasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_custom(self, client, mock_stub):
        """Test list_tasks with custom parameters."""
        mock_response = MagicMock()
        mock_stub.ListTasks.return_value = mock_response

        response = await client.list_tasks(
            filter_status=1,  # TASK_STATUS_RUNNING
            limit=50,
            offset=10,
            include_completed=False,
        )

        assert response == mock_response
        mock_stub.ListTasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check(self, client, mock_stub):
        """Test health_check."""
        mock_response = MagicMock()
        mock_stub.HealthCheck.return_value = mock_response

        response = await client.health_check()

        assert response == mock_response
        mock_stub.HealthCheck.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_runtime_status(self, client, mock_stub):
        """Test get_runtime_status."""
        mock_response = MagicMock()
        mock_stub.GetRuntimeStatus.return_value = mock_response

        response = await client.get_runtime_status(include_metrics=True)

        assert response == mock_response
        mock_stub.GetRuntimeStatus.assert_called_once()


class TestCheckpointServiceClient:
    """Tests for CheckpointServiceClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create mock CheckpointServiceStub."""
        stub = MagicMock()
        stub.SaveCheckpoint = AsyncMock()
        stub.GetCheckpoint = AsyncMock()
        stub.ListCheckpoints = AsyncMock()
        stub.GetLatestCheckpoint = AsyncMock()
        stub.CheckpointHealth = AsyncMock()
        return stub

    @pytest.fixture
    def client(self, mock_stub):
        """Create CheckpointServiceClient with mock stub."""
        return CheckpointServiceClient(mock_stub)

    @pytest.mark.asyncio
    async def test_save_checkpoint(self, client, mock_stub):
        """Test save_checkpoint."""
        mock_response = MagicMock()
        mock_stub.SaveCheckpoint.return_value = mock_response

        response = await client.save_checkpoint(
            thread_id=str(uuid4()),
            checkpoint_type=1,  # CHECKPOINT_TYPE_LOCAL
            state_blob=b"state",
            channel_values=b"values",
            pending_sends=b"sends",
            metadata="metadata",
            task_id=str(uuid4()),
        )

        assert response == mock_response
        mock_stub.SaveCheckpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_checkpoint(self, client, mock_stub):
        """Test get_checkpoint."""
        mock_response = MagicMock()
        mock_stub.GetCheckpoint.return_value = mock_response

        checkpoint_id = str(uuid4())
        response = await client.get_checkpoint(checkpoint_id)

        assert response == mock_response
        mock_stub.GetCheckpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, client, mock_stub):
        """Test list_checkpoints."""
        mock_response = MagicMock()
        mock_stub.ListCheckpoints.return_value = mock_response

        thread_id = str(uuid4())
        response = await client.list_checkpoints(thread_id, limit=100, offset=0)

        assert response == mock_response
        mock_stub.ListCheckpoints.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_checkpoint(self, client, mock_stub):
        """Test get_latest_checkpoint."""
        mock_response = MagicMock()
        mock_stub.GetLatestCheckpoint.return_value = mock_response

        thread_id = str(uuid4())
        response = await client.get_latest_checkpoint(thread_id)

        assert response == mock_response
        mock_stub.GetLatestCheckpoint.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check(self, client, mock_stub):
        """Test health_check."""
        mock_response = MagicMock()
        mock_stub.CheckpointHealth.return_value = mock_response

        response = await client.health_check()

        assert response == mock_response
        mock_stub.CheckpointHealth.assert_called_once()


class TestWorkerServiceClient:
    """Tests for WorkerServiceClient."""

    @pytest.fixture
    def mock_stub(self):
        """Create mock WorkerExecutorStub."""
        stub = MagicMock()
        stub.ExecuteTask = AsyncMock()
        stub.HealthCheck = AsyncMock()
        return stub

    @pytest.fixture
    def client(self, mock_stub):
        """Create WorkerServiceClient with mock stub."""
        return WorkerServiceClient(mock_stub)

    @pytest.mark.asyncio
    async def test_execute_task(self, client, mock_stub):
        """Test execute_task."""
        mock_response = MagicMock()
        mock_stub.ExecuteTask.return_value = mock_response

        task_id = str(uuid4())
        payload = '{"key": "value"}'
        response = await client.execute_task(task_id, payload=payload)

        assert response == mock_response
        mock_stub.ExecuteTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_task_with_metadata(self, client, mock_stub):
        """Test execute_task with metadata."""
        mock_response = MagicMock()
        mock_stub.ExecuteTask.return_value = mock_response

        task_id = str(uuid4())
        metadata = {"worker_id": "test-worker"}
        response = await client.execute_task(task_id, metadata=metadata)

        assert response == mock_response
        mock_stub.ExecuteTask.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check(self, client, mock_stub):
        """Test health_check."""
        mock_response = MagicMock()
        mock_stub.HealthCheck.return_value = mock_response

        worker_id = "test-worker"
        response = await client.health_check(worker_id)

        assert response == mock_response
        mock_stub.HealthCheck.assert_called_once()


class TestGRPCClient:
    """Tests for GRPCClient wrapper."""

    @pytest.fixture
    def mock_grpc_module(self):
        """Create mock grpc module with all dependencies."""
        mock_grpc = MagicMock()
        mock_aio_channel = MagicMock()
        mock_grpc.aio.channel.return_value = mock_aio_channel
        mock_grpc.aio.channel.close = AsyncMock()

        # Create mock stubs
        mock_runtime_stub = MagicMock()
        mock_checkpoint_stub = MagicMock()
        mock_worker_stub = MagicMock()

        # Create mock grpc modules
        mock_runtime_grpc = MagicMock()
        mock_checkpoint_grpc = MagicMock()
        mock_worker_grpc = MagicMock()

        mock_runtime_grpc.RuntimeServiceStub.return_value = mock_runtime_stub
        mock_checkpoint_grpc.CheckpointServiceStub.return_value = mock_checkpoint_stub
        mock_worker_grpc.WorkerExecutorStub.return_value = mock_worker_stub

        # Create proto modules
        mock_runtime_pb2 = MagicMock()
        mock_checkpoint_pb2 = MagicMock()
        mock_worker_pb2 = MagicMock()

        # Mock the imports inside connect()
        with patch.dict('sys.modules', {
            'grpc': mock_grpc,
            'grpc.aio': mock_grpc.aio,
            'app.proto.runtime_pb2_grpc': mock_runtime_grpc,
            'app.proto.checkpoint_pb2_grpc': mock_checkpoint_grpc,
            'app.proto.worker_pb2_grpc': mock_worker_grpc,
            'app.proto.runtime_pb2': mock_runtime_pb2,
            'app.proto.checkpoint_pb2': mock_checkpoint_pb2,
            'app.proto.worker_pb2': mock_worker_pb2,
        }):
            yield {
                'grpc': mock_grpc,
                'channel': mock_aio_channel,
                'runtime_stub': mock_runtime_stub,
                'checkpoint_stub': mock_checkpoint_stub,
                'worker_stub': mock_worker_stub,
            }

    @pytest.mark.asyncio
    async def test_connect(self, mock_grpc_module):
        """Test connect establishes gRPC connection."""
        client = GRPCClient()

        await client.connect()

        assert client.is_connected is True
        assert client.runtime is not None
        assert client.checkpoint is not None
        assert client.worker is not None

    @pytest.mark.asyncio
    async def test_connect_with_custom_config(self, mock_grpc_module):
        """Test connect with custom configuration."""
        config = GRPCClientConfig(
            host="127.0.0.1",
            port=50052,
            connection_timeout=10.0,
        )
        client = GRPCClient(config=config)

        await client.connect()

        assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_close(self, mock_grpc_module):
        """Test close closes gRPC connection."""
        client = GRPCClient()

        await client.connect()
        
        # Get the mock channel from the fixture
        mock_channel = mock_grpc_module['channel']
        await client.close()

        assert client.is_connected is False
        # Verify the channel close was called
        assert mock_channel.close.called

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_grpc_module):
        """Test async context manager."""
        async with GRPCClient() as client:
            assert client.is_connected is True

        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_health_check_all_services(self, mock_channel, mock_stubs):
        """Test health_check checks all services."""
        mock_stubs["runtime"].HealthCheck = AsyncMock()
        mock_stubs["checkpoint"].CheckpointHealth = AsyncMock()
        mock_stubs["worker"].HealthCheck = AsyncMock()

        client = GRPCClient()
        await client.connect()

        result = await client.health_check()

        assert result is True
        mock_stubs["runtime"].HealthCheck.assert_called_once()
        mock_stubs["checkpoint"].CheckpointHealth.assert_called_once()
        mock_stubs["worker"].HealthCheck.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_channel, mock_stubs):
        """Test health_check when a service fails."""
        mock_stubs["runtime"].HealthCheck = AsyncMock(side_effect=Exception("Service unavailable"))

        client = GRPCClient()
        await client.connect()

        result = await client.health_check()

        assert result is False
