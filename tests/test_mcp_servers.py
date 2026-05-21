"""Tests for MCP system server tools."""
import pytest
import asyncio
import json
import tempfile
import os

from core.mcp.servers.filesystem import read_file, write_file, list_directory, search_files
from core.mcp.servers.shell import execute_command, run_script
from core.mcp.servers.cloud_api import http_request


class TestFilesystemServer:
    async def _test_read_write_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.txt")
            # Write
            result = await write_file(test_file, "hello world")
            assert "written" in result.lower() or "File written" in result

            # Read
            content = await read_file(test_file)
            assert content == "hello world"

            # List
            listing = await list_directory(tmpdir)
            assert "test.txt" in listing

    def test_read_write_list(self):
        asyncio.run(self._test_read_write_list())

    async def _test_search_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            await write_file(os.path.join(tmpdir, "a.py"), "x = 1")
            await write_file(os.path.join(tmpdir, "b.txt"), "hello")
            result = await search_files(tmpdir, "*.py")
            assert "a.py" in result

    def test_search_files(self):
        asyncio.run(self._test_search_files())

    def test_read_nonexistent_file(self):
        result = asyncio.run(read_file("/nonexistent/path/file.txt"))
        assert "not found" in result.lower() or "Error" in result


class TestShellServer:
    def test_execute_command_echo(self):
        result = asyncio.run(execute_command("echo hello"))
        assert "hello" in result

    def test_execute_command_blocked(self):
        result = asyncio.run(execute_command("rm -rf /"))
        assert "blocked" in result.lower() or "Error" in result

    def test_run_script_python(self):
        result = asyncio.run(run_script("print(2+2)", interpreter="python"))
        assert "4" in result


class TestCloudApiServer:
    def test_http_request_to_example(self):
        result = asyncio.run(http_request("https://example.com"))
        # Should return HTML or an error
        assert isinstance(result, str)
        assert len(result) > 0 or "Error" in result


class TestBrowserServer:
    def test_browser_server_tools_importable(self):
        from core.mcp.servers.browser import launch, navigate, screenshot, close
        assert callable(launch)
        assert callable(navigate)
        assert callable(screenshot)
        assert callable(close)

    @pytest.mark.asyncio
    async def test_browser_launch_navigate_screenshot_close(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from core.mcp.servers.browser import launch, navigate, screenshot, close

        mock_session = MagicMock()
        mock_session.launch = AsyncMock(return_value=MagicMock(success=True, result={"page": "ok"}))
        mock_session.navigate = AsyncMock(return_value=MagicMock(success=True, result={"url": "https://example.com"}))
        mock_session.screenshot = AsyncMock(return_value=MagicMock(success=True, result={"path": "/tmp/ss.png"}))
        mock_session.close_context_only = AsyncMock(return_value=MagicMock(success=True, result={"message": "closed"}))

        mock_mgr = MagicMock()
        mock_mgr.get_or_create_session = AsyncMock(return_value=mock_session)
        mock_mgr.close_session = AsyncMock(return_value=MagicMock(success=True, result={"message": "closed"}))

        with patch("core.mcp.servers.browser.browser_session_manager", mock_mgr):
            result = await launch(task_id="t1", headless=True)
            assert '"success": true' in result

            result = await navigate(task_id="t1", url="https://example.com")
            assert '"success": true' in result

            result = await screenshot(task_id="t1", path="/tmp/ss.png")
            assert '"success": true' in result

            result = await close(task_id="t1")
            assert '"success": true' in result


class TestDocumentServer:
    def test_document_server_tools_importable(self):
        from core.mcp.servers.document import parse, parse_pdf, parse_txt, chunk, summarize
        assert callable(parse)
        assert callable(parse_pdf)
        assert callable(parse_txt)
        assert callable(chunk)
        assert callable(summarize)

    @pytest.mark.asyncio
    async def test_document_parse_txt(self):
        from core.mcp.servers.document import parse_txt
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello from MCP document server")
            path = f.name
        try:
            result = await parse_txt(path=path)
            data = json.loads(result)
            assert data["success"] is True
            assert "Hello from MCP document server" in data["result"]["text"]
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_document_chunk(self):
        from core.mcp.servers.document import chunk
        result = await chunk(text="Hello world. This is a test.", chunk_size=10, overlap=2)
        data = json.loads(result)
        assert data["success"] is True
        assert len(data["result"]["chunks"]) > 0


class TestCodeServer:
    def test_code_server_tools_importable(self):
        from core.mcp.servers.code import run_python
        assert callable(run_python)

    @pytest.mark.asyncio
    async def test_code_run_python(self):
        from core.mcp.servers.code import run_python
        code = "result = 21 * 2"
        result = await run_python(code=code, timeout=10)
        data = json.loads(result)
        assert data["success"] is True
        assert data["result"] == 42
