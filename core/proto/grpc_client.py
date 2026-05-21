"""gRPC client wrapper for AgentOS Python runtime.

Provides client stubs for supervisor communication while maintaining
LangGraph checkpoint compatibility and SQLite persistence for local mode.

Supports TLS + API key authentication for desktop mode.

Usage:
    from core.proto.grpc_client import GRPCClient
    
    client = GRPCClient(host="localhost", port=50052, use_tls=True)
    await client.connect()
    
    # Create a task
    response = await client.runtime.create_task(
        query="Navigate to example.com",
        task_type="TASK_TYPE_SIMPLE"
    )
    
    # Get checkpoint
    checkpoint = await client.checkpoint.get_checkpoint(checkpoint_id="123")
    
    await client.close()
"""

import os
from typing import Dict, Optional
from dataclasses import dataclass

import grpc

from ..logs.logger import logger

# gRPC stub modules - imported at module level for testability
from ..proto import runtime_pb2_grpc
from ..proto import checkpoint_pb2_grpc
from ..proto import worker_pb2_grpc


@dataclass
class GRPCClientConfig:
    """Configuration for gRPC client."""
    host: str = "localhost"
    port: int = 50052
    max_send_message_length: int = 50 * 1024 * 1024  # 50MB
    max_receive_message_length: int = 50 * 1024 * 1024  # 50MB
    connection_timeout: float = 5.0
    keepalive_timeout: int = 60
    use_tls: bool = True
    ca_cert_path: Optional[str] = None
    client_cert_path: Optional[str] = None
    client_key_path: Optional[str] = None
    api_key: Optional[str] = None


class RuntimeServiceClient:
    """Client for RuntimeService gRPC calls."""

    def __init__(self, stub):
        self._stub = stub

    async def create_task(
        self,
        query: str,
        task_type: int = 1,  # TASK_TYPE_SIMPLE
        require_approval: bool = False,
        timeout_seconds: int = 300,
        parent_task_id: str = "",
        config: Optional[Dict[str, str]] = None
    ):
        """Create a new task."""
        from ..proto import runtime_pb2

        request = runtime_pb2.CreateTaskRequest(
            query=query,
            type=task_type,  # Proto field is 'type', not 'task_type'
            require_approval=require_approval,
            timeout_seconds=timeout_seconds,
            parent_task_id=parent_task_id,
            config=config or {}
        )
        return await self._stub.CreateTask(request)

    async def get_task(self, task_id: str):
        """Get task by ID."""
        from ..proto import runtime_pb2

        request = runtime_pb2.GetTaskRequest(task_id=task_id)
        return await self._stub.GetTask(request)

    async def cancel_task(self, task_id: str, reason: str = ""):
        """Cancel a task."""
        from ..proto import runtime_pb2

        request = runtime_pb2.CancelTaskRequest(task_id=task_id, reason=reason)
        return await self._stub.CancelTask(request)

    async def list_tasks(
        self,
        filter_status: int = 0,  # TASK_STATUS_UNSPECIFIED
        limit: int = 100,
        offset: int = 0,
        include_completed: bool = True
    ):
        """List tasks with optional filtering."""
        from ..proto import runtime_pb2

        request = runtime_pb2.ListTasksRequest(
            filter_status=filter_status,
            limit=limit,
            offset=offset,
            include_completed=include_completed
        )
        return await self._stub.ListTasks(request)

    async def health_check(self):
        """Health check endpoint."""
        from ..proto import runtime_pb2

        request = runtime_pb2.HealthCheckRequest()
        return await self._stub.HealthCheck(request)

    async def get_runtime_status(self, include_metrics: bool = False):
        """Get runtime status."""
        from ..proto import runtime_pb2

        request = runtime_pb2.GetRuntimeStatusRequest(include_metrics=include_metrics)
        return await self._stub.GetRuntimeStatus(request)


class CheckpointServiceClient:
    """Client for CheckpointService gRPC calls."""

    def __init__(self, stub):
        self._stub = stub

    async def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_type: int = 1,  # CHECKPOINT_TYPE_LOCAL
        state_blob: bytes = b"",
        channel_values: bytes = b"",
        pending_sends: bytes = b"",
        parent_ids: Optional[list] = None,
        metadata: str = "",
        task_id: str = ""
    ):
        """Save checkpoint state."""
        from ..proto import checkpoint_pb2

        request = checkpoint_pb2.SaveCheckpointRequest(
            thread_id=thread_id,
            checkpoint_type=checkpoint_type,
            state_blob=state_blob,
            channel_values=channel_values,
            pending_sends=pending_sends,
            parent_ids=parent_ids or [],
            metadata=metadata,
            task_id=task_id
        )
        return await self._stub.SaveCheckpoint(request)

    async def get_checkpoint(self, checkpoint_id: str):
        """Get checkpoint by ID."""
        from ..proto import checkpoint_pb2

        request = checkpoint_pb2.GetCheckpointRequest(checkpoint_id=checkpoint_id)
        return await self._stub.GetCheckpoint(request)

    async def list_checkpoints(
        self,
        thread_id: str,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = True
    ):
        """List checkpoints for a thread."""
        from ..proto import checkpoint_pb2

        request = checkpoint_pb2.ListCheckpointsRequest(
            thread_id=thread_id,
            limit=limit,
            offset=offset,
            include_metadata=include_metadata
        )
        return await self._stub.ListCheckpoints(request)

    async def get_latest_checkpoint(self, thread_id: str, include_metadata: bool = True):
        """Get latest checkpoint for a thread."""
        from ..proto import checkpoint_pb2

        request = checkpoint_pb2.GetLatestCheckpointRequest(
            thread_id=thread_id,
            include_metadata=include_metadata
        )
        return await self._stub.GetLatestCheckpoint(request)

    async def health_check(self):
        """Health check endpoint."""
        from ..proto import checkpoint_pb2

        request = checkpoint_pb2.CheckpointHealthRequest()
        return await self._stub.CheckpointHealth(request)


class WorkerServiceClient:
    """Client for WorkerService gRPC calls."""

    def __init__(self, stub):
        self._stub = stub

    async def execute_task(
        self,
        task_id: str,
        task_type: str = "mcp_tool_call",
        payload: str = "",
        timeout_seconds: int = 300,
        metadata: Optional[Dict[str, str]] = None
    ):
        """Execute a task."""
        from ..proto import worker_pb2

        request = worker_pb2.TaskRequest(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {}
        )
        return await self._stub.ExecuteTask(request)

    async def health_check(self, worker_id: str = ""):
        """Health check endpoint."""
        from ..proto import worker_pb2

        request = worker_pb2.HealthRequest(worker_id=worker_id)
        return await self._stub.HealthCheck(request)


class APIKeyInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    """Interceptor that adds API key to every gRPC call."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        metadata = list(client_call_details.metadata or [])
        metadata.append(("x-api-key", self._api_key))
        client_call_details = client_call_details._replace(metadata=metadata)
        return await continuation(client_call_details, request)


class GRPCClient:
    """gRPC client wrapper for AgentOS runtime.
    
    Provides client stubs for supervisor communication while maintaining
    LangGraph checkpoint compatibility and SQLite persistence for local mode.
    Supports TLS + API key authentication.
    """

    def __init__(self, config: Optional[GRPCClientConfig] = None):
        self._config = config or GRPCClientConfig()
        self._channel = None
        self._runtime_service = None
        self._checkpoint_service = None
        self._worker_service = None
        self._connected = False

    @property
    def runtime(self) -> RuntimeServiceClient:
        """RuntimeService client."""
        return self._runtime_service

    @property
    def checkpoint(self) -> CheckpointServiceClient:
        """CheckpointService client."""
        return self._checkpoint_service

    @property
    def worker(self) -> WorkerServiceClient:
        """WorkerService client."""
        return self._worker_service

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    def _load_api_key(self) -> Optional[str]:
        """Load API key from config or environment."""
        if self._config.api_key:
            return self._config.api_key
        return os.environ.get("AGENTOS_API_KEY")

    def _is_desktop_mode(self) -> bool:
        """Check if running in desktop-native gRPC mode."""
        mode = os.environ.get("AGENTOS_RUNTIME_MODE", os.environ.get("RUNTIME_MODE", "http"))
        return mode.lower() == "grpc"

    def _enforce_mtls(self) -> bool:
        """Check if mTLS should be strictly enforced.

        mTLS is ONLY enforced when AGENTOS_ENFORCE_MTLS=true is explicitly set.
        The presence of certificates alone enables mTLS but does not enforce it,
        allowing tests and development environments to work without strict requirements.
        """
        return os.environ.get("AGENTOS_ENFORCE_MTLS", "").lower() == "true"

    def _build_channel(self) -> grpc.aio.Channel:
        """Build gRPC channel with TLS and auth.

        In desktop mode with AGENTOS_ENFORCE_MTLS=true, mTLS is mandatory.
        If certificates are missing, the connection will fail.
        """
        target = f"{self._config.host}:{self._config.port}"
        is_desktop = self._is_desktop_mode()
        enforce_mtls = self._enforce_mtls()

        options = [
            ("grpc.max_send_message_length", self._config.max_send_message_length),
            ("grpc.max_receive_message_length", self._config.max_receive_message_length),
            ("grpc.keepalive_timeout_ms", self._config.keepalive_timeout * 1000),
        ]

        api_key = self._load_api_key()
        interceptors = []
        if api_key:
            interceptors.append(APIKeyInterceptor(api_key))

        if self._config.use_tls:
            # Load CA certificate
            ca_cert_path = self._config.ca_cert_path or self._default_ca_path()
            if not os.path.exists(ca_cert_path):
                if is_desktop and enforce_mtls:
                    raise RuntimeError(
                        f"DESKTOP SECURITY: CA certificate not found at {ca_cert_path}. "
                        f"mTLS is mandatory in desktop mode. Run 'agentos init-certs' to generate certificates."
                    )
                logger.warning(f"CA cert not found at {ca_cert_path}, falling back to insecure channel")
                channel = grpc.aio.insecure_channel(target, options=options, interceptors=interceptors)
                return channel

            with open(ca_cert_path, "rb") as f:
                ca_cert = f.read()

            creds = grpc.ssl_channel_credentials(ca_cert)

            # Add client cert for mTLS if available
            client_cert_path = self._config.client_cert_path or self._default_client_cert_path()
            client_key_path = self._config.client_key_path or self._default_client_key_path()
            has_client_cert = os.path.exists(client_cert_path) and os.path.exists(client_key_path)

            if has_client_cert:
                with open(client_cert_path, "rb") as f:
                    client_cert = f.read()
                with open(client_key_path, "rb") as f:
                    client_key = f.read()
                creds = grpc.ssl_channel_credentials(ca_cert, client_key, client_cert)
                logger.info(f"gRPC client using mTLS to {target}")
            else:
                if is_desktop and enforce_mtls:
                    raise RuntimeError(
                        f"DESKTOP SECURITY: Client certificate not found at {client_cert_path} or key at {client_key_path}. "
                        f"mTLS is mandatory in desktop mode. Run 'agentos init-certs' to generate certificates."
                    )
                logger.info(f"gRPC client using TLS (no client cert) to {target}")

            channel = grpc.aio.secure_channel(target, creds, options=options, interceptors=interceptors)
            return channel
        else:
            channel = grpc.aio.insecure_channel(target, options=options, interceptors=interceptors)
            if is_desktop:
                logger.warning(f"gRPC client using INSECURE connection in desktop mode to {target}")
            return channel

    def _default_ca_path(self) -> str:
        """Get default CA certificate path."""
        home = os.path.expanduser("~")
        return os.path.join(home, ".agentos", "certs", "ca.crt")

    def _default_client_cert_path(self) -> str:
        """Get default client certificate path."""
        home = os.path.expanduser("~")
        return os.path.join(home, ".agentos", "certs", "client.crt")

    def _default_client_key_path(self) -> str:
        """Get default client key path."""
        home = os.path.expanduser("~")
        return os.path.join(home, ".agentos", "certs", "client.key")

    async def connect(self):
        """Establish gRPC connection to supervisor."""
        try:
            self._channel = self._build_channel()

            # Create stubs
            runtime_stub = runtime_pb2_grpc.RuntimeServiceStub(self._channel)
            checkpoint_stub = checkpoint_pb2_grpc.CheckpointServiceStub(self._channel)
            worker_stub = worker_pb2_grpc.WorkerExecutorStub(self._channel)

            # Initialize service clients
            self._runtime_service = RuntimeServiceClient(runtime_stub)
            self._checkpoint_service = CheckpointServiceClient(checkpoint_stub)
            self._worker_service = WorkerServiceClient(worker_stub)

            self._connected = True
            logger.info(f"gRPC client connected to {self._config.host}:{self._config.port}")

        except Exception as e:
            logger.error(f"Failed to connect to gRPC server: {e}")
            raise

    async def close(self):
        """Close gRPC connection."""
        if self._channel:
            await self._channel.close()
            self._connected = False
            logger.info("gRPC client disconnected")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False

    async def health_check(self) -> bool:
        """Check if supervisor is healthy."""
        if not self._connected:
            return False

        try:
            # Check runtime and worker services
            await self._runtime_service.health_check()
            await self._worker_service.health_check()
            return True
        except Exception as e:
            logger.error(f"gRPC health check failed: {e}")
            return False
