#!/usr/bin/env python3
"""
Integration Test Suite for AgentOS gRPC Communication
Tests end-to-end communication between Python runtime and Go supervisor
"""

import pytest
import asyncio
import subprocess
import sys
import time
import tempfile
import os
from datetime import datetime
from pathlib import Path

# Import proto modules
from app.proto import checkpoint_pb2, runtime_pb2, worker_pb2

# Test server startup and shutdown
class TestGRPCServerLifecycle:
    """Test gRPC server lifecycle management."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_checkpoints.db")
            yield db_path
    
    @pytest.mark.asyncio
    async def test_server_startup(self, temp_db_path):
        """Test that gRPC server starts successfully."""
        from app.runtime.grpc_server import GRPCServer
        from app.langgraph.sqlite_checkpointer import SQLiteCheckpointSaver
        
        # Create checkpointer with temp database
        checkpointer = SQLiteCheckpointSaver(db_path=temp_db_path)
        
        server = GRPCServer(host="127.0.0.1", port=50051, checkpointer=checkpointer)
        
        # Start server
        await server.start()
        
        assert server._server is not None
        assert server._runtime is not None
        assert server._orchestrator is not None
        assert server._checkpointer is not None
        
        # Clean up
        await server.stop()
    
    @pytest.mark.asyncio
    async def test_server_shutdown(self, temp_db_path):
        """Test that gRPC server shuts down gracefully."""
        from app.runtime.grpc_server import GRPCServer
        from app.langgraph.sqlite_checkpointer import SQLiteCheckpointSaver
        
        checkpointer = SQLiteCheckpointSaver(db_path=temp_db_path)
        server = GRPCServer(host="127.0.0.1", port=50052, checkpointer=checkpointer)
        
        await server.start()
        await server.stop(grace=1.0)
        
        assert server._server is None
        assert server._runtime is None


# Test service implementations
class TestServiceImplementations:
    """Test individual gRPC service implementations."""
    
    @pytest.mark.asyncio
    async def test_runtime_service_health_check(self):
        """Test RuntimeService health check."""
        from app.runtime.grpc_server import GRPCServer, RuntimeServiceImpl
        from app.runtime.runtime import AgentRuntime
        from app.orchestrator.core import Orchestrator
        
        # Initialize components
        runtime = AgentRuntime()
        await runtime.initialize()
        orchestrator = Orchestrator()
        
        service = RuntimeServiceImpl(runtime, orchestrator)
        
        # Mock context for gRPC
        class MockContext:
            def __init__(self):
                self._code = None
                self._details = None
            
            def abort(self, code, details):
                self._code = code
                self._details = details
                raise Exception(details)
        
        context = MockContext()
        
        # Test health check
        response = await service.HealthCheck(None, context)
        
        assert response.healthy is True
        assert response.version == "0.2.0"
    
    @pytest.mark.asyncio
    async def test_checkpoint_service_save_get(self, temp_db_path):
        """Test CheckpointService save and get operations."""
        from app.runtime.grpc_server import CheckpointServiceImpl
        from app.langgraph.sqlite_checkpointer import SQLiteCheckpointSaver
        
        checkpointer = SQLiteCheckpointSaver(db_path=temp_db_path)
        
        service = CheckpointServiceImpl(checkpointer)
        
        # Mock context
        class MockContext:
            def abort(self, code, details):
                raise Exception(details)
        
        context = MockContext()
        
        # Test save checkpoint
        response = await service.SaveCheckpoint(
            checkpoint_pb2.SaveCheckpointRequest(
                thread_id="test-thread-123",
                checkpoint_json='{"key": "value"}',
                metadata_json='{"test": true}'
            ),
            context
        )
        
        assert response.success is True
        assert response.thread_id == "test-thread-123"
        
        # Test get checkpoint
        get_response = await service.GetCheckpoint(
            checkpoint_pb2.GetCheckpointRequest(
                thread_id="test-thread-123"
            ),
            context
        )
        
        assert get_response.success is True
        assert get_response.thread_id == "test-thread-123"


# Test client-server communication
class TestClientServerCommunication:
    """Test gRPC client-server communication patterns."""
    
    @pytest.mark.asyncio
    async def test_grpc_client_connection(self):
        """Test gRPC client can connect to server."""
        from app.proto.grpc_client import GRPCClient, GRPCClientConfig
        
        config = GRPCClientConfig(host="127.0.0.1", port=50053)
        client = GRPCClient(config)
        
        # Start server in background
        from app.runtime.grpc_server import GRPCServer
        server = GRPCServer(host="127.0.0.1", port=50053)
        
        # Start server
        await server.start()
        
        try:
            # Connect client
            await client.connect()
            
            assert client.is_connected is True
            
            # Test health check
            is_healthy = await client.health_check()
            assert is_healthy is True
            
        finally:
            # Cleanup
            await client.close()
            await server.stop()


# Test end-to-end task execution
class TestEndToEndTaskExecution:
    """Test complete task execution flow via gRPC."""
    
    @pytest.mark.asyncio
    async def test_create_task_via_grpc(self):
        """Test creating a task through gRPC."""
        from app.proto.grpc_client import GRPCClient, GRPCClientConfig
        from app.runtime.grpc_server import GRPCServer
        
        # Start server
        server = GRPCServer(host="127.0.0.1", port=50054)
        await server.start()
        
        try:
            # Create client
            config = GRPCClientConfig(host="127.0.0.1", port=50054)
            client = GRPCClient(config)
            await client.connect()
            
            # Test create task
            response = await client.runtime.create_task(
                query="Test task via gRPC",
                task_type=1,
                require_approval=False,
                timeout_seconds=300,
                parent_task_id="",
                config={"test": True}
            )
            
            assert response is not None
            
        finally:
            await client.close()
            await server.stop()


# Test concurrent operations
class TestConcurrentOperations:
    """Test concurrent gRPC operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """Test multiple concurrent health checks."""
        from app.runtime.grpc_server import GRPCServer, RuntimeServiceImpl
        from app.runtime.runtime import AgentRuntime
        from app.orchestrator.core import Orchestrator
        
        # Initialize components
        runtime = AgentRuntime()
        await runtime.initialize()
        orchestrator = Orchestrator()
        
        service = RuntimeServiceImpl(runtime, orchestrator)
        
        # Mock context
        class MockContext:
            def abort(self, code, details):
                raise Exception(details)
        
        context = MockContext()
        
        # Run 10 concurrent health checks
        tasks = [service.HealthCheck(None, context) for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        
        assert len(responses) == 10
        assert all(r.healthy is True for r in responses)


# Test error handling
class TestErrorHandling:
    """Test gRPC error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_invalid_port_error(self):
        """Test connection error handling."""
        from app.proto.grpc_client import GRPCClient, GRPCClientConfig
        
        config = GRPCClientConfig(host="localhost", port=9999)
        client = GRPCClient(config)
        
        with pytest.raises(Exception):
            await client.connect()
        
        assert client.is_connected is False


# Test checkpoint persistence
class TestCheckpointPersistence:
    """Test checkpoint persistence via gRPC."""
    
    @pytest.mark.asyncio
    async def test_checkpoint_lifecycle(self, temp_db_path):
        """Test complete checkpoint lifecycle."""
        from app.runtime.grpc_server import GRPCServer, CheckpointServiceImpl
        from app.langgraph.sqlite_checkpointer import SQLiteCheckpointSaver
        
        checkpointer = SQLiteCheckpointSaver(db_path=temp_db_path)
        service = CheckpointServiceImpl(checkpointer)
        
        # Mock context
        class MockContext:
            def abort(self, code, details):
                raise Exception(details)
        
        context = MockContext()
        
        # Save checkpoint
        save_response = await service.SaveCheckpoint(
            checkpoint_pb2.SaveCheckpointRequest(
                thread_id="lifecycle-thread",
                checkpoint_json='{"state": "running"}',
                metadata_json='{"step": 1}'
            ),
            context
        )
        
        assert save_response.success is True
        checkpoint_id = save_response.checkpoint_id
        
        # Get checkpoint
        get_response = await service.GetCheckpoint(
            checkpoint_pb2.GetCheckpointRequest(
                thread_id="lifecycle-thread",
                checkpoint_id=checkpoint_id
            ),
            context
        )
        
        assert get_response.success is True
        assert "state" in get_response.checkpoint_json
        
        # List checkpoints
        list_response = await service.ListCheckpoints(
            checkpoint_pb2.ListCheckpointsRequest(
                thread_id="lifecycle-thread"
            ),
            context
        )
        
        assert list_response.success is True
        assert list_response.count >= 1


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
