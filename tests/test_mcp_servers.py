"""Tests for MCP system server tools."""
import pytest
import asyncio
import tempfile
import os

from app.mcp.servers.filesystem import read_file, write_file, list_directory, search_files
from app.mcp.servers.shell import execute_command, run_script
from app.mcp.servers.cloud_api import http_request


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
