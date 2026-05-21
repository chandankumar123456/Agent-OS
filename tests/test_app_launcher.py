"""Tests for deterministic app launcher."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.environments.app_launcher import (
    _normalize_app_name,
    _APP_NAME_MAP,
    resolve_app_path,
    is_process_running,
    launch_application,
    LaunchResult,
)


class TestAppNameNormalization:
    def test_normalize_basic(self):
        assert _normalize_app_name("Notepad") == "notepad"
        assert _normalize_app_name("  Chrome  ") == "chrome"
        assert _normalize_app_name("notepad.exe") == "notepad"

    def test_common_mappings_exist(self):
        assert "notepad" in _APP_NAME_MAP
        assert "chrome" in _APP_NAME_MAP
        assert "vscode" in _APP_NAME_MAP
        assert "whatsapp" in _APP_NAME_MAP
        assert _APP_NAME_MAP["notepad"] == "notepad.exe"
        assert _APP_NAME_MAP["chrome"] == "chrome.exe"


class TestResolveAppPath:
    def test_direct_path(self, tmp_path):
        exe = tmp_path / "myapp.exe"
        exe.write_text("fake")
        assert resolve_app_path(str(exe)) == str(exe)

    def test_common_name_map(self):
        # notepad.exe should resolve via shutil.which on Windows
        if sys.platform == "win32":
            result = resolve_app_path("notepad")
            assert result is not None
            assert "notepad" in result.lower()

    def test_unknown_app_returns_none(self):
        result = resolve_app_path("this_app_definitely_does_not_exist_12345")
        assert result is None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows registry test")
    def test_registry_search(self):
        # chrome or edge should be resolvable via registry on most Windows systems
        result = resolve_app_path("chrome") or resolve_app_path("edge") or resolve_app_path("notepad")
        assert result is not None


class TestIsProcessRunning:
    def test_notepad_running(self):
        if sys.platform != "win32":
            pytest.skip("Windows only")
        # We can't guarantee notepad is running, but we can test the function doesn't crash
        result = is_process_running("notepad.exe")
        assert isinstance(result, bool)

    def test_nonexistent_process(self):
        result = is_process_running("nonexistent_process_12345.exe")
        assert result is False


class TestLaunchApplication:
    @pytest.mark.asyncio
    async def test_launch_notepad_and_verify(self):
        if sys.platform != "win32":
            pytest.skip("Windows only")
        result = await launch_application("notepad", timeout=5.0, verify_window=True)
        # Cleanup: close notepad if it opened
        if result.success and result.pid:
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
            except Exception:
                pass
        assert result.success is True
        assert result.process_path is not None

    @pytest.mark.asyncio
    async def test_launch_unknown_app_fails(self):
        result = await launch_application("nonexistent_app_xyz_12345", timeout=2.0)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_launch_result_to_dict(self):
        result = LaunchResult(
            success=True,
            process_path="C:\\Windows\\notepad.exe",
            pid=1234,
            window_info={"title": "Untitled - Notepad"},
            method="direct",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["process_path"] == "C:\\Windows\\notepad.exe"
        assert d["pid"] == 1234
        assert d["window"]["title"] == "Untitled - Notepad"
        assert d["method"] == "direct"


class TestFallbackUILaunch:
    @pytest.mark.asyncio
    async def test_fallback_ui_launch_win32(self):
        if sys.platform != "win32":
            pytest.skip("Windows only")
        from core.environments.app_launcher import _fallback_ui_launch
        # Use calc since it's lightweight
        result = await _fallback_ui_launch("calc", "calc.exe", timeout=5.0, verify_window=True)
        if result.success:
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "CalculatorApp.exe"], capture_output=True)
            except Exception:
                pass
        # Fallback may or may not succeed depending on environment; just verify it doesn't crash
        assert isinstance(result.success, bool)
