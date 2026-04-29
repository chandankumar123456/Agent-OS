"""Action V1 Benchmark Suite.

Benchmarks:
1. open notepad and write hello world
2. open chrome and search latest AI news
3. search AI news → summarize → save file
4. find healthy breakfast → create static webpage → save file
5. open calculator
6. switch between browser and notepad
"""
from __future__ import annotations

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.action_v1.runner import ActionV1Runner
from app.action_v1.models import ActionStatus, Capability
from app.action_v1.selector import CapabilitySelector
from app.action_v1.executor import DeterministicExecutor
from app.action_v1.verifier import DeterministicVerifier


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def runner():
    return ActionV1Runner()


@pytest.fixture
def selector():
    return CapabilitySelector()


# ── Benchmark 1: open notepad and write hello world ──────────────────

@pytest.mark.asyncio
async def test_benchmark_1_open_notepad_write_hello_world(runner):
    """Benchmark 1: open notepad and write hello world"""
    with patch.object(runner.executor, "_invoke_tool", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {"success": True, "result": {"pid": 1234}}

        result = await runner.run("task-1", "open notepad and write hello world", {})

        assert result.status == ActionStatus.SUCCESS
        calls = [c[0][0] for c in mock_invoke.call_args_list]
        assert "desktop_env__open_application" in calls
        assert "desktop_env__type_text" in calls
        # Verify text content
        type_call = [c for c in mock_invoke.call_args_list if c[0][0] == "desktop_env__type_text"][0]
        assert type_call[0][1]["text"] == "hello world"


# ── Benchmark 2: open chrome and search latest AI news ───────────────

@pytest.mark.asyncio
async def test_benchmark_2_open_chrome_search_ai_news(runner):
    """Benchmark 2: open chrome and search latest AI news"""
    with patch.object(runner.executor, "_invoke_tool", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {"success": True, "result": {}}

        result = await runner.run("task-2", "open chrome and search latest AI news", {})

        assert result.status == ActionStatus.SUCCESS
        calls = [c[0][0] for c in mock_invoke.call_args_list]
        assert "browser_env__launch" in calls
        assert "browser_env__navigate" in calls
        assert "browser_env__type" in calls
        assert "browser_env__click" in calls
        assert "browser_env__get_text" in calls
        # Verify navigate to google.com (not URL shortcut)
        nav_call = [c for c in mock_invoke.call_args_list if c[0][0] == "browser_env__navigate"][0]
        assert "google.com" in nav_call[0][1]["url"].lower()
        # Verify search query was typed
        type_call = [c for c in mock_invoke.call_args_list if c[0][0] == "browser_env__type"][0]
        assert "latest AI news" in type_call[0][1]["text"]


# ── Benchmark 3: search AI news → summarize → save file ──────────────

@pytest.mark.asyncio
async def test_benchmark_3_search_summarize_save(runner):
    """Benchmark 3: search AI news → summarize → save file"""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="Summary:\nAI breakthrough today. New model released.")
    runner.executor._llm_client = mock_llm

    with patch.object(runner.executor, "_invoke_tool", new_callable=AsyncMock) as mock_invoke:
        # First call: cloud search, second: write file
        mock_invoke.side_effect = [
            {"success": True, "result": {"headlines": ["AI breakthrough today", "New model released"]}},
            {"success": True, "result": {"output": "File written"}},
        ]

        result = await runner.run("task-3", "search AI news then summarize and save file", {})

        assert result.status == ActionStatus.SUCCESS
        calls = [c[0][0] for c in mock_invoke.call_args_list]
        assert "cloud_api__search_web" in calls
        assert "filesystem__write_file" in calls


# ── Benchmark 4: find healthy breakfast → create static webpage → save ─

@pytest.mark.asyncio
async def test_benchmark_4_breakfast_webpage(runner):
    """Benchmark 4: find healthy breakfast options → create static webpage → save file"""
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(
        return_value="<!DOCTYPE html><html><body><h1>Cheapest Healthy Breakfast Options</h1><p>Oatmeal, eggs, toast</p></body></html>"
    )
    runner.executor._llm_client = mock_llm

    with patch.object(runner.executor, "_invoke_tool", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.side_effect = [
            {"success": True, "result": {"results": ["oatmeal", "eggs"]}},
            {"success": True, "result": {"output": "File written"}},
        ]

        result = await runner.run(
            "task-4",
            "find cheapest healthy breakfast options, create a static page on it",
            {},
        )

        assert result.status == ActionStatus.SUCCESS
        calls = [c[0][0] for c in mock_invoke.call_args_list]
        assert "cloud_api__search_web" in calls
        assert "filesystem__write_file" in calls
        # Verify HTML content was written
        write_call = [c for c in mock_invoke.call_args_list if c[0][0] == "filesystem__write_file"][0]
        content = write_call[0][1]["content"]
        assert "<html" in content
        assert "Breakfast" in content or "breakfast" in content


# ── Benchmark 5: open calculator ─────────────────────────────────────

@pytest.mark.asyncio
async def test_benchmark_5_open_calculator(runner):
    """Benchmark 5: open calculator"""
    with patch.object(runner.executor, "_invoke_tool", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {"success": True, "result": {"pid": 5678}}

        result = await runner.run("task-5", "open calculator", {})

        assert result.status == ActionStatus.SUCCESS
        calls = [c[0][0] for c in mock_invoke.call_args_list]
        assert "desktop_env__open_application" in calls
        app_call = [c for c in mock_invoke.call_args_list if c[0][0] == "desktop_env__open_application"][0]
        assert app_call[0][1]["app_name"] == "calc"


# ── Benchmark 6: switch between browser and notepad ──────────────────

@pytest.mark.asyncio
async def test_benchmark_6_switch_browser_notepad(runner):
    """Benchmark 6: switch between browser and notepad"""
    with patch.object(runner.executor, "_invoke_tool", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = {"success": True, "result": {}}

        result = await runner.run("task-6", "switch between browser and notepad", {})

        assert result.status == ActionStatus.SUCCESS
        # Should at least attempt desktop window operations
        calls = [c[0][0] for c in mock_invoke.call_args_list]
        assert any("desktop" in c for c in calls) or any("browser" in c for c in calls)


# ── Capability Selector Tests ────────────────────────────────────────

def test_selector_browser(selector):
    assert selector.classify("open chrome and search AI news") == Capability.BROWSER

def test_selector_desktop(selector):
    assert selector.classify("open notepad and write hello world") == Capability.DESKTOP

def test_selector_filesystem(selector):
    assert selector.classify("create a file called notes.txt") == Capability.FILESYSTEM

def test_selector_multistep(selector):
    assert selector.classify("search AI news and summarize and save file") == Capability.MULTI_STEP


# ── Deterministic Verification Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_verifier_file_exists():
    verifier = DeterministicVerifier()
    from app.action_v1.models import ActionResult, ActionStatus, ExecutionContext, Capability
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test")
        path = f.name

    result = ActionResult(
        status=ActionStatus.SUCCESS,
        task_id="t1",
        output={"file_path": path},
    )
    ctx = ExecutionContext(task_id="t1", query="test", capability=Capability.FILESYSTEM)
    verified = await verifier.verify(ctx, result)
    assert verified.verification_passed is True

    import os
    os.remove(path)
