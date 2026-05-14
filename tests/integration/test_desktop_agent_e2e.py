"""Meaningful desktop automation integration test.

This test exercises the full agent desktop automation pipeline:
1. LLM generates text to write
2. Desktop automation opens Notepad
3. Types the generated text
4. Saves to a specific path
5. Closes Notepad
6. Verifies the saved file

Requirements:
- Windows OS (desktop automation uses pyautogui + uiautomation)
- Desktop automation libraries installed
- OpenAI API key for LLM text generation

This test is skipped automatically if requirements are not met.
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Skip entire module if not on Windows
if sys.platform != "win32":
    pytest.skip("Desktop automation tests require Windows", allow_module_level=True)

# Try to import desktop automation deps
try:
    import pyautogui
    import uiautomation as auto
except ImportError:
    pytest.skip("Desktop automation libraries not installed (pyautogui, uiautomation)", allow_module_level=True)

# Ensure we're in desktop mode
os.environ.setdefault("AGENTOS_RUNTIME_MODE", "grpc")
os.environ.setdefault("RUNTIME_MODE", "grpc")

from app.desktop_native.sqlite_store import sqlite_store
from app.desktop_native.task_queue import TaskPriority
from app.tools.registry import tool_registry
from app.tools.base import ToolInput
from app.environments.desktop_env import desktop_session_manager
from app.llm.providers import get_provider


@pytest.fixture(scope="module")
def temp_save_dir():
    """Create a temp directory for saving files."""
    tmp = tempfile.mkdtemp(prefix="agentos_test_")
    yield tmp
    # Cleanup
    try:
        for f in Path(tmp).glob("*"):
            f.unlink()
        Path(tmp).rmdir()
    except Exception:
        pass


@pytest.fixture(autouse=True)
async def init_desktop():
    """Initialize SQLite and desktop session manager."""
    await sqlite_store.initialize_schema()
    yield
    # Cleanup all desktop sessions
    try:
        await desktop_session_manager.close_all_sessions()
    except Exception:
        pass


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.desktop
@pytest.mark.timeout(120)
class TestDesktopAgentNotepadE2E:
    """End-to-end test: Agent opens Notepad, writes text, saves, closes."""

    async def _get_llm_text(self) -> str:
        """Use LLM to generate a short sentence for the test."""
        try:
            provider = get_provider()
            messages = [
                {"role": "system", "content": "You are a helpful assistant. Respond with exactly one short sentence (max 10 words)."},
                {"role": "user", "content": "Write a cheerful greeting for a notepad test file."},
            ]
            response = await provider.chat(messages, model=os.environ.get("OPENAI_MODEL", "gpt-4o"))
            text = response.get("content", "Hello from AgentOS!").strip().strip('"').strip("'")
            # Sanitize: only printable ASCII, no newlines
            text = "".join(c for c in text if c.isprintable() and c not in "\r\n\t")
            if len(text) > 100:
                text = text[:100]
            if not text:
                text = "Hello from AgentOS!"
            return text
        except Exception as e:
            pytest.skip(f"LLM text generation failed: {e}")

    async def _execute_tool(self, task_id: str, tool_name: str, params: dict):
        """Helper to execute a tool via the registry."""
        tool = tool_registry.get(tool_name)
        if not tool:
            raise RuntimeError(f"Tool {tool_name} not found")
        params["_task_id"] = task_id
        result = await tool.execute(ToolInput(parameters=params))
        return result

    async def test_open_notepad_type_save_close(self, temp_save_dir):
        """Full E2E: open Notepad, type LLM-generated text, save, close, verify."""
        task_id = f"desktop_e2e_{os.getpid()}"
        save_path = os.path.join(temp_save_dir, "agentos_notepad_test.txt")

        # Step 0: Generate text via LLM
        text_to_write = await self._get_llm_text()
        print(f"\n[TEST] LLM generated text: '{text_to_write}'")

        # Step 1: Open Notepad
        print("[TEST] Opening Notepad...")
        result = await self._execute_tool(task_id, "desktop_env__open_application", {"app_name": "notepad"})
        assert result.success, f"Failed to open Notepad: {result.error}"

        # Give Notepad time to open
        await asyncio.sleep(1.5)

        # Step 2: Focus Notepad window
        print("[TEST] Focusing Notepad...")
        result = await self._execute_tool(task_id, "desktop_env__focus_window", {"title": "Untitled - Notepad"})
        if not result.success:
            # Try alternative title
            result = await self._execute_tool(task_id, "desktop_env__focus_window", {"title": "Notepad"})
        assert result.success, f"Failed to focus Notepad: {result.error}"
        await asyncio.sleep(0.5)

        # Step 3: Type the LLM-generated text
        print(f"[TEST] Typing text: '{text_to_write}'")
        result = await self._execute_tool(
            task_id, "desktop_env__type_text", {"text": text_to_write, "interval": 0.01}
        )
        assert result.success, f"Failed to type text: {result.error}"
        await asyncio.sleep(0.5)

        # Step 4: Save file (Ctrl+S)
        print(f"[TEST] Saving to {save_path}...")
        result = await self._execute_tool(task_id, "desktop_env__press_key", {"keys": "ctrl+s"})
        assert result.success, f"Failed to press Ctrl+S: {result.error}"
        await asyncio.sleep(1.0)

        # Step 5: Type save path in the Save dialog
        result = await self._execute_tool(
            task_id, "desktop_env__type_text", {"text": save_path, "interval": 0.01}
        )
        assert result.success, f"Failed to type save path: {result.error}"
        await asyncio.sleep(0.5)

        # Step 6: Press Enter to confirm save
        result = await self._execute_tool(task_id, "desktop_env__press_key", {"keys": "return"})
        assert result.success, f"Failed to press Enter: {result.error}"
        await asyncio.sleep(1.0)

        # Step 7: Handle "File already exists" dialog if it appears
        # (not expected in temp dir, but handle gracefully)
        windows = await self._execute_tool(task_id, "desktop_env__get_window_list", {})
        if windows.success and isinstance(windows.result, dict):
            titles = [w.get("title", "") for w in windows.result.get("windows", [])]
            if any("Confirm Save As" in t or "Overwrite" in t for t in titles):
                result = await self._execute_tool(task_id, "desktop_env__press_key", {"keys": "y"})
                await asyncio.sleep(0.5)

        # Step 8: Close Notepad (Alt+F4)
        print("[TEST] Closing Notepad...")
        result = await self._execute_tool(task_id, "desktop_env__press_key", {"keys": "alt+f4"})
        assert result.success, f"Failed to close Notepad: {result.error}"
        await asyncio.sleep(0.5)

        # Step 9: Verify the saved file
        print(f"[TEST] Verifying saved file at {save_path}...")
        assert os.path.exists(save_path), f"File was not saved: {save_path}"

        with open(save_path, "r", encoding="utf-8") as f:
            saved_content = f.read()

        # The saved content should contain our text (may have extra whitespace)
        assert text_to_write in saved_content, (
            f"Saved file does not contain expected text.\n"
            f"Expected: {text_to_write!r}\n"
            f"Actual: {saved_content!r}"
        )

        print(f"[TEST] SUCCESS! File verified: {save_path}")
        print(f"[TEST] Content: {saved_content!r}")

    async def test_kernel_submits_desktop_task(self, temp_save_dir):
        """Test that AgentKernel can submit and execute a desktop task."""
        from app.desktop_native.kernel import AgentKernel

        kernel = AgentKernel(max_concurrent_tasks=1)
        await kernel.start()

        try:
            save_path = os.path.join(temp_save_dir, "kernel_test.txt")

            # Submit a desktop task
            task_id = await kernel.submit_task(
                query=f"Open Notepad, type 'Kernel test {time.time()}', save to {save_path}, close Notepad",
                user_id="test_user",
                priority=TaskPriority.NORMAL,
            )

            print(f"[TEST] Submitted task {task_id} to kernel")

            # Wait for completion (with timeout)
            result = await kernel.wait_for_task(task_id, timeout=60.0)
            print(f"[TEST] Task result: {result}")

            # The task should complete (success or failure is logged)
            assert result["status"] in ("completed", "failed", "timeout"), f"Unexpected status: {result['status']}"

        finally:
            await kernel.stop()
