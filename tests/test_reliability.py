"""Reliability and failure injection tests for Sprint 3."""
import pytest
import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch


# ── 1. MCP stdout corruption ──────────────────────────────────────────

class TestMcpStdoutSanitization:
    """Validate that MCP stdio servers do not corrupt JSON-RPC transport."""

    def test_stdio_sanitize_patches_print(self):
        import builtins
        import core.mcp.servers._stdio_sanitize as sanitize
        # print should now default to stderr
        assert builtins.print is not sanitize._orig_print

    def test_stdio_sanitize_logging_uses_stderr(self):
        import logging
        root = logging.getLogger()
        stderr_handlers = [
            h for h in root.handlers
            if hasattr(h, "stream") and h.stream is sys.stderr
        ]
        assert len(stderr_handlers) > 0, "Root logger must have at least one stderr handler"

    def test_stdio_sanitize_noisy_loggers_suppressed(self):
        import logging
        for name in ("comtypes", "httpx", "httpcore", "openai"):
            logger = logging.getLogger(name)
            assert logger.level >= logging.WARNING, f"{name} logger level should be >= WARNING"


# ── 2. Browser crash / failure injection ──────────────────────────────

@pytest.mark.asyncio
async def test_browser_session_handles_crash_gracefully():
    from core.environments.browser_env import BrowserSession
    session = BrowserSession("crash-test")

    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=True)  # Simulate crash
    mock_page.url = "about:blank"
    session._page = mock_page

    # get_text should handle closed page gracefully
    result = await session.get_text()
    assert result.success is False or result.result is not None


@pytest.mark.asyncio
async def test_browser_navigate_invalid_url():
    from core.environments.browser_env import BrowserSession
    session = BrowserSession("nav-test")
    # No browser context bound yet
    result = await session.navigate("not-a-valid-url")
    assert result.success is False


# ── 3. Document corruption / malformed input ──────────────────────────

@pytest.mark.asyncio
async def test_document_parse_corrupted_pdf():
    from core.mcp.servers.document import parse_pdf
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4\nThis is not a real PDF")
        path = f.name
    try:
        result = await parse_pdf(path=path)
        data = json.loads(result)
        # Should not crash; may succeed with empty text or fail gracefully
        assert "success" in data
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_document_parse_nonexistent_file():
    from core.mcp.servers.document import parse
    result = await parse(path="/nonexistent/path/file.txt")
    data = json.loads(result)
    assert data["success"] is False
    assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_document_chunk_empty_text():
    from core.mcp.servers.document import chunk
    result = await chunk(text="", chunk_size=100)
    data = json.loads(result)
    assert data["success"] is True
    assert data["result"]["chunks"] == [""]


# ── 4. Code execution safety / infinite loop ──────────────────────────

@pytest.mark.asyncio
async def test_code_execution_respects_timeout():
    from core.mcp.servers.code import run_python
    from core.tools.sandbox import ToolSandbox

    # Mock sandbox to simulate timeout without spinning a real thread
    with patch.object(ToolSandbox, "run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = MagicMock(
            success=False, error="Tool code_executor__run_python timed out after 1s"
        )
        result = await run_python(code="while True: pass", timeout=1)

    data = json.loads(result)
    assert data["success"] is False
    assert "timed out" in data["error"].lower() or "timeout" in data["error"].lower()


@pytest.mark.asyncio
async def test_code_execution_blocks_import():
    from core.mcp.servers.code import run_python
    code = "import os"
    result = await run_python(code=code)
    data = json.loads(result)
    assert data["success"] is False
    assert "security" in data["error"].lower() or "import" in data["error"].lower()


@pytest.mark.asyncio
async def test_code_execution_blocks_dangerous_builtins():
    from core.mcp.servers.code import run_python
    code = "result = eval('1+1')"
    result = await run_python(code=code)
    data = json.loads(result)
    assert data["success"] is False


# ── 5. Filesystem permission failure ──────────────────────────────────

@pytest.mark.asyncio
async def test_filesystem_write_to_readonly_path():
    from core.mcp.servers.filesystem import write_file
    # Attempt to write to a path that is outside allowed directories
    result = await write_file(path="Z:\\nonexistent\\readonly_test_agentos", content="test")
    assert "error" in result.lower() or "Error" in result or "outside" in result.lower()


# ── 6. MCP server crash / transport failure ───────────────────────────

@pytest.mark.asyncio
async def test_mcp_client_manager_handles_server_disconnect():
    from core.mcp.client_manager import MCPClientManager
    manager = MCPClientManager()
    # Start with no connections
    assert manager.connections == {}
    # Disconnect all should not raise
    await manager.disconnect_all()
    assert manager.connections == {}


@pytest.mark.asyncio
async def test_registry_execute_handles_missing_tool_gracefully():
    from core.tools.registry import tool_registry
    result = await tool_registry.execute("nonexistent_tool__12345", {})
    assert result.success is False
    assert "not found" in result.error.lower()


# ── 7. Recovery engine without Redis ──────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_engine_degrades_without_redis():
    from core.capabilities.recovery import RecoveryEngine
    from core.capabilities.models import RecoveryAction

    engine = RecoveryEngine(max_retries=2)

    with patch("core.capabilities.recovery.redis_client") as mock_redis:
        mock_redis.client = None

        decision = await engine.decide(
            task_id="t1", step_id="s1",
            error="timeout connecting to server",
            current_tool="browser_env__navigate",
        )
        assert decision.action == RecoveryAction.RETRY
        assert decision.task_id == "t1"

        # Second retry
        decision = await engine.decide(
            task_id="t1", step_id="s1",
            error="timeout connecting to server",
            current_tool="browser_env__navigate",
        )
        assert decision.action == RecoveryAction.RETRY

        # Third attempt should escalate (max_retries=2 means 2 retries max)
        decision = await engine.decide(
            task_id="t1", step_id="s1",
            error="timeout connecting to server",
            current_tool="browser_env__navigate",
        )
        assert decision.action == RecoveryAction.ESCALATE


@pytest.mark.asyncio
async def test_recovery_engine_switch_tool_fallback():
    from core.capabilities.recovery import RecoveryEngine
    from core.capabilities.models import RecoveryAction

    engine = RecoveryEngine()
    decision = await engine.decide(
        task_id="t1", step_id="s1",
        error="tool execution failed",
        current_tool="filesystem__write_file",
    )
    assert decision.action == RecoveryAction.SWITCH_TOOL
    assert decision.next_tool == "shell__execute_command"


@pytest.mark.asyncio
async def test_recovery_engine_replan_on_tool_not_found():
    from core.capabilities.recovery import RecoveryEngine
    from core.capabilities.models import RecoveryAction

    engine = RecoveryEngine()
    decision = await engine.decide(
        task_id="t1", step_id="s1",
        error="tool not found: unknown_tool",
    )
    assert decision.action == RecoveryAction.REPLAN


# ── 8. Observability resilience ───────────────────────────────────────

@pytest.mark.asyncio
async def test_observability_bus_survives_db_failure():
    from core.observability.bus import ObservabilityBus
    from core.observability.models import ObservabilityEvent, ObservabilityEventType

    bus = ObservabilityBus()

    event = ObservabilityEvent(
        event_type=ObservabilityEventType.TOOL_INVOKED,
        task_id="test-task",
        trace_id="trace-1",
        step_id="s1",
        payload={"tool": "test_tool"},
        source="test",
    )

    with patch("core.observability.bus.span_repo") as mock_repo:
        mock_repo.create = AsyncMock(side_effect=RuntimeError("Database session factory is unavailable"))
        # Should not raise
        await bus.emit(event)


@pytest.mark.asyncio
async def test_observability_emit_safe_swallows_all_errors():
    from core.observability.bus import ObservabilityBus
    from core.observability.models import ObservabilityEventType

    bus = ObservabilityBus()
    with patch.object(bus, "emit", side_effect=Exception("boom")):
        # Should not raise
        await bus.emit_safe(
            ObservabilityEventType.TOOL_INVOKED,
            task_id="test",
            payload={},
            source="test",
        )


# ── 9. Verification engine retry flags ────────────────────────────────

@pytest.mark.asyncio
async def test_verification_retryable_flags():
    from core.capabilities.verification import DeterministicVerificationEngine
    engine = DeterministicVerificationEngine()

    # File not found should be retryable
    result = await engine._verify_file_exists({"path": "/nonexistent/path"})
    assert result[1].get("retryable") is True


# ── 10. End-to-end corruption check ───────────────────────────────────

@pytest.mark.asyncio
async def test_benchmark_end_to_end_no_transport_corruption():
    """Validate that MCP servers start and tool calls complete without stdout corruption."""
    from core.mcp.client_manager import MCPClientManager
    from core.tools.registry import tool_registry

    manager = MCPClientManager()
    await manager.start_system_servers()
    await tool_registry.discover_mcp_tools()

    tools = await manager.list_tools()
    tool_names = {t["name"] for t in tools}

    # All 7 system servers should expose tools
    assert len(tool_names) >= 10, f"Expected >= 10 tools, got {len(tool_names)}: {tool_names}"

    # Execute a quick tool call via the local manager and verify it returns clean JSON
    call_result = await manager.call_tool("document__chunk", {"text": "hello world", "chunk_size": 5})
    content = ""
    if hasattr(call_result, "content"):
        content = "\n".join(
            str(c.text if hasattr(c, "text") else c)
            for c in call_result.content
        )
    result_data = json.loads(content)
    assert result_data.get("success") is True, f"MCP tool failed: {result_data.get('error')}"

    await manager.disconnect_all()
