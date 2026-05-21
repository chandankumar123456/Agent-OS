"""Tests for local tool fallbacks that work without MCP servers running."""
import os
import tempfile

import pytest

# Ensure test env is set before any app imports
os.environ.setdefault("AGENTOS_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-env-32chars!!")
os.environ.setdefault("RUNTIME_MODE", "grpc")
os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")

from core.tools.local_fallbacks import (
    local_read_file,
    local_write_file,
    local_list_directory,
    local_search_files,
    local_execute_command,
    local_run_script,
    _is_safe,
    _resolve_path,
)


@pytest.mark.asyncio
async def test_read_file_success():
    """Test reading a file that exists."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", dir="/tmp", delete=False) as f:
        f.write("hello world")
        path = f.name
    try:
        result = await local_read_file(path)
        assert result == "hello world"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_read_file_not_found():
    """Test reading a file that does not exist."""
    result = await local_read_file("/tmp/nonexistent_test_file_xyz.txt")
    assert "Error: File not found" in result


@pytest.mark.asyncio
async def test_write_file_success():
    """Test writing a file creates it with correct content."""
    path = "/tmp/test_tool_fallback_write.txt"
    try:
        result = await local_write_file(path, "test content 123")
        assert "File written" in result
        with open(path, "r") as f:
            assert f.read() == "test content 123"
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_write_file_creates_directories():
    """Test writing a file creates parent directories."""
    path = "/tmp/test_fallback_subdir/nested/file.txt"
    try:
        result = await local_write_file(path, "nested content")
        assert "File written" in result
        assert os.path.exists(path)
    finally:
        if os.path.exists(path):
            os.unlink(path)
        # Cleanup directories
        import shutil
        if os.path.exists("/tmp/test_fallback_subdir"):
            shutil.rmtree("/tmp/test_fallback_subdir")


@pytest.mark.asyncio
async def test_list_directory():
    """Test listing directory contents."""
    result = await local_list_directory("/tmp")
    assert result  # /tmp is never empty
    assert "Error" not in result


@pytest.mark.asyncio
async def test_list_directory_not_found():
    """Test listing a directory that does not exist."""
    result = await local_list_directory("/tmp/nonexistent_dir_xyz_test")
    assert "Error: Path not found" in result


@pytest.mark.asyncio
async def test_search_files():
    """Test searching for files by glob pattern."""
    # Create a temp file to search for
    path = "/tmp/test_search_fallback_abc.txt"
    try:
        with open(path, "w") as f:
            f.write("searchable")
        result = await local_search_files("/tmp", "test_search_fallback_abc.txt")
        assert path in result
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.mark.asyncio
async def test_execute_command_success():
    """Test executing a simple shell command."""
    result = await local_execute_command("echo hello")
    assert "hello" in result


@pytest.mark.asyncio
async def test_execute_command_with_cwd():
    """Test executing a command with a specific working directory."""
    result = await local_execute_command("pwd", cwd="/tmp")
    assert "/tmp" in result


@pytest.mark.asyncio
async def test_execute_command_blocked():
    """Test that unsafe commands are blocked."""
    result = await local_execute_command("rm -rf /")
    assert "Error: Command blocked for safety" in result


@pytest.mark.asyncio
async def test_execute_command_dd_blocked():
    """Test that dd command is blocked."""
    result = await local_execute_command("dd if=/dev/zero of=/tmp/test")
    assert "Error: Command blocked for safety" in result


@pytest.mark.asyncio
async def test_run_script_bash():
    """Test running a bash script."""
    result = await local_run_script("echo 'script output'", interpreter="bash")
    assert "script output" in result


@pytest.mark.asyncio
async def test_is_safe_allows_safe_commands():
    """Test that safe commands pass the safety check."""
    assert _is_safe("echo hello") is True
    assert _is_safe("ls -la") is True
    assert _is_safe("cat /tmp/test.txt") is True
    assert _is_safe("python3 -c 'print(1)'") is True


@pytest.mark.asyncio
async def test_is_safe_blocks_dangerous_commands():
    """Test that dangerous commands are blocked."""
    assert _is_safe("rm file.txt") is False
    assert _is_safe("dd if=/dev/zero of=/dev/sda") is False
    assert _is_safe("mkfs.ext4 /dev/sda1") is False
    assert _is_safe("fdisk /dev/sda") is False


@pytest.mark.asyncio
async def test_resolve_path_outside_safe_roots():
    """Test that paths outside safe roots are rejected."""
    with pytest.raises(ValueError, match="outside allowed directories"):
        _resolve_path("/etc/shadow")


@pytest.mark.asyncio
async def test_read_file_outside_safe_roots():
    """Test that reading outside safe roots returns an error."""
    result = await local_read_file("/etc/shadow")
    assert "Error reading file" in result
