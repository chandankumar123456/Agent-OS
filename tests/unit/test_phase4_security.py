"""Phase 4 Security & Safety Hardening validation tests.

Tests the desktop-native security model:
- LocalAuth (OS identity + local API key)
- CapabilityManager (capability tokens with approval)
- Sandbox (restricted subprocess execution)
- mTLS enforcement in gRPC client
"""

import asyncio
import os
import sys

import pytest
import pytest_asyncio

os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")
os.environ.setdefault("RUNTIME_MODE", "grpc")

from app.desktop_native.local_auth import local_auth, LocalAuth
from app.desktop_native.capability_manager import (
    capability_manager,
    CapabilityManager,
    CapabilityScope,
    CapabilityStatus,
    SENSITIVE_CAPABILITIES,
)
from app.desktop_native.sandbox import sandbox, Sandbox, SandboxResult
from app.desktop_native.sqlite_store import sqlite_store


@pytest_asyncio.fixture(autouse=True)
async def init_sqlite():
    await sqlite_store.initialize_schema()
    yield


class TestLocalAuth:
    @pytest.mark.asyncio
    async def test_initialize_generates_key(self):
        auth = LocalAuth()
        key = await auth.initialize()
        assert key.startswith("aos_")
        assert len(key) > 10

    @pytest.mark.asyncio
    async def test_validate_key(self):
        auth = LocalAuth()
        # Revoke any existing keys first to ensure clean state
        await auth.revoke_all_keys()
        key = await auth.initialize()
        assert await auth.validate_key(key) is True
        assert await auth.validate_key("invalid_key") is False
        assert await auth.validate_key("") is False

    @pytest.mark.asyncio
    async def test_get_current_identity(self):
        auth = LocalAuth()
        identity = auth.get_current_identity()
        assert "user_name" in identity
        assert "machine_id" in identity
        assert "platform" in identity
        assert identity["platform"] == sys.platform

    @pytest.mark.asyncio
    async def test_revoke_all_keys(self):
        auth = LocalAuth()
        await auth.initialize()
        count = await auth.revoke_all_keys()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_is_authorized(self):
        auth = LocalAuth()
        assert await auth.is_authorized("user") is True
        assert await auth.is_authorized("admin") is True


class TestCapabilityManager:
    @pytest.mark.asyncio
    async def test_request_non_sensitive_capability(self):
        mgr = CapabilityManager()
        token = await mgr.request_capability(
            target="web_search",
            task_id="task-1",
            scope=CapabilityScope.TOOL,
        )
        assert token is not None
        assert token.status == CapabilityStatus.APPROVED
        assert token.target == "web_search"

    @pytest.mark.asyncio
    async def test_request_sensitive_capability(self):
        mgr = CapabilityManager()
        token = await mgr.request_capability(
            target="desktop_env__open_application",
            task_id="task-2",
            scope=CapabilityScope.TOOL,
        )
        assert token is not None
        # Sensitive capabilities are auto-approved in desktop mode (with logging)
        assert token.status == CapabilityStatus.APPROVED

    @pytest.mark.asyncio
    async def test_use_capability(self):
        mgr = CapabilityManager()
        token = await mgr.request_capability(
            target="web_search",
            task_id="task-3",
            scope=CapabilityScope.TOOL,
            max_uses=2,
        )
        assert await mgr.use_capability(token.token_id) is True
        assert await mgr.use_capability(token.token_id) is True
        # Third use should fail (max uses reached)
        assert await mgr.use_capability(token.token_id) is False

    @pytest.mark.asyncio
    async def test_capability_expiry(self):
        mgr = CapabilityManager()
        token = await mgr.request_capability(
            target="web_search",
            task_id="task-4",
            scope=CapabilityScope.TOOL,
            expires_in_minutes=-1,  # Already expired
        )
        # Should still create but be expired on use
        assert token is not None
        assert await mgr.use_capability(token.token_id) is False

    @pytest.mark.asyncio
    async def test_revoke_capability(self):
        mgr = CapabilityManager()
        token = await mgr.request_capability(
            target="web_search",
            task_id="task-5",
            scope=CapabilityScope.TOOL,
        )
        await mgr.revoke_capability(token.token_id)
        revoked = await mgr.get_capability(token.token_id)
        assert revoked.status == CapabilityStatus.REVOKED

    @pytest.mark.asyncio
    async def test_get_active_capability(self):
        mgr = CapabilityManager()
        await mgr.request_capability(
            target="web_search",
            task_id="task-6",
            scope=CapabilityScope.TOOL,
        )
        active = await mgr.get_active_capability("web_search", "task-6")
        assert active is not None
        assert active.target == "web_search"

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        mgr = CapabilityManager()
        await mgr.request_capability(
            target="web_search",
            task_id="task-7",
            scope=CapabilityScope.TOOL,
            expires_in_minutes=-1,
        )
        count = await mgr.cleanup_expired()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_list_pending(self):
        mgr = CapabilityManager()
        pending = await mgr.list_pending()
        assert isinstance(pending, list)


class TestSandbox:
    @pytest.mark.asyncio
    async def test_run_echo_command(self):
        if sys.platform == "win32":
            result = await sandbox.run("echo hello", timeout=5)
        else:
            result = await sandbox.run("echo hello", timeout=5)
        assert result.success is True
        assert "hello" in result.stdout.lower()
        assert result.return_code == 0

    @pytest.mark.asyncio
    async def test_run_timeout(self):
        # Use Python sleep for cross-platform timeout testing
        result = await sandbox.run(
            f"{sys.executable} -c \"import time; time.sleep(10)\"",
            timeout=2,
        )
        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error.lower() or result.return_code == -1

    @pytest.mark.asyncio
    async def test_run_python_code(self):
        result = await sandbox.run_python("print(2+2)", timeout=5)
        assert result.success is True
        assert "4" in result.stdout

    @pytest.mark.asyncio
    async def test_run_shell_command(self):
        if sys.platform == "win32":
            result = await sandbox.run_shell("dir", timeout=5)
        else:
            result = await sandbox.run_shell("ls", timeout=5)
        assert result.success is True
        assert result.stdout != ""


class TestMTLSEnforcement:
    @pytest.mark.asyncio
    async def test_desktop_mode_requires_tls(self):
        """Verify that gRPC client enforces mTLS when AGENTOS_ENFORCE_MTLS=true."""
        from app.proto.grpc_client import GRPCClient, GRPCClientConfig

        os.environ["AGENTOS_ENFORCE_MTLS"] = "true"
        try:
            # In desktop mode with enforce_mtls, missing certs should raise RuntimeError
            client = GRPCClient(
                GRPCClientConfig(
                    host="localhost",
                    port=50051,
                    use_tls=True,
                    ca_cert_path="/nonexistent/ca.crt",
                    client_cert_path="/nonexistent/client.crt",
                    client_key_path="/nonexistent/client.key",
                )
            )

            with pytest.raises(RuntimeError) as exc_info:
                client._build_channel()

            assert "DESKTOP SECURITY" in str(exc_info.value)
            assert "mTLS is mandatory" in str(exc_info.value)
        finally:
            os.environ.pop("AGENTOS_ENFORCE_MTLS", None)

    def test_sensitive_capabilities_defined(self):
        assert "desktop_env__open_application" in SENSITIVE_CAPABILITIES
        assert "shell__execute" in SENSITIVE_CAPABILITIES
        assert "filesystem__delete_file" in SENSITIVE_CAPABILITIES
