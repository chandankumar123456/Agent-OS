"""Tests for WorkflowCheckpoint dataclass and MultiAppOrchestrator class.

Phase 5: Validates checkpoint creation, serialization, orchestrator init,
state introspection, file transfer error handling, and app switching
graceful degradation — all with session managers and subprocess mocked.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from core.environments.multi_app_orchestrator import (
    WorkflowCheckpoint,
    MultiAppOrchestrator,
)
from core.environments.window_registry import WindowRegistry
from core.tools.base import ToolOutput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator():
    """Return a MultiAppOrchestrator with OS-level calls mocked out."""
    orch = MultiAppOrchestrator(task_id="test-task-001")
    # Replace the lazy-loaded window_registry with a mock-free instance
    orch._window_registry = _make_mock_registry()
    # Clean up any stale persisted checkpoint from previous test runs
    checkpoint_path = os.path.join(
        MultiAppOrchestrator.CHECKPOINT_DIR, "checkpoint_test-task-001.json"
    )
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
    yield orch
    # Teardown: clean up persisted checkpoint
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)


def _make_mock_registry():
    """Create a WindowRegistry with __init__ mocked to avoid logger import issues."""
    with patch.object(WindowRegistry, "__init__", lambda self: None):
        reg = WindowRegistry.__new__(WindowRegistry)
        reg._registry = {}
        reg._logger = MagicMock()
        return reg


# ---------------------------------------------------------------------------
# 1. test_checkpoint_creation
# ---------------------------------------------------------------------------

def test_checkpoint_creation():
    """Create a WorkflowCheckpoint and verify all fields."""
    cp = WorkflowCheckpoint(
        task_id="task-1",
        step="step-1",
        active_app="notepad",
        active_window="ref-abc",
        browser_url="https://example.com",
        browser_tab_title="Example",
        desktop_file_path="/tmp/test.txt",
        open_files=["/tmp/test.txt"],
        open_windows=[{"ref_id": "ref-abc", "title": "Notepad"}],
    )

    assert cp.task_id == "task-1"
    assert cp.step == "step-1"
    assert cp.active_app == "notepad"
    assert cp.active_window == "ref-abc"
    assert cp.browser_url == "https://example.com"
    assert cp.browser_tab_title == "Example"
    assert cp.desktop_file_path == "/tmp/test.txt"
    assert cp.open_files == ["/tmp/test.txt"]
    assert len(cp.open_windows) == 1
    # created_at / updated_at should be auto-set
    assert cp.created_at != ""
    assert cp.updated_at != ""


def test_checkpoint_creation_minimal():
    """Minimal checkpoint with only required fields."""
    cp = WorkflowCheckpoint(task_id="task-2", step="init")

    assert cp.task_id == "task-2"
    assert cp.step == "init"
    assert cp.active_app is None
    assert cp.active_window is None
    assert cp.browser_url is None
    assert cp.open_files == []
    assert cp.open_windows == []


# ---------------------------------------------------------------------------
# 2. test_checkpoint_to_dict
# ---------------------------------------------------------------------------

def test_checkpoint_to_dict():
    """Verify to_dict() round-trip preserves all fields."""
    cp = WorkflowCheckpoint(
        task_id="task-3",
        step="step-2",
        active_app="browser",
        browser_url="https://google.com",
        open_files=["/a/b.txt"],
    )

    d = cp.to_dict()

    assert d["task_id"] == "task-3"
    assert d["step"] == "step-2"
    assert d["active_app"] == "browser"
    assert d["browser_url"] == "https://google.com"
    assert d["open_files"] == ["/a/b.txt"]
    assert d["created_at"] == cp.created_at
    assert d["updated_at"] == cp.updated_at
    # Ensure all expected keys are present
    expected_keys = {
        "task_id", "step", "active_app", "active_window",
        "browser_url", "browser_tab_title", "desktop_file_path",
        "open_files", "open_windows", "created_at", "updated_at",
    }
    assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# 3. test_orchestrator_init
# ---------------------------------------------------------------------------

def test_orchestrator_init():
    """Create an orchestrator and verify task_id is set."""
    orch = MultiAppOrchestrator(task_id="my-task-42")

    assert orch.task_id == "my-task-42"
    assert orch._checkpoints == []
    assert orch._current_checkpoint is None


# ---------------------------------------------------------------------------
# 4. test_orchestrator_get_state
# ---------------------------------------------------------------------------

def test_orchestrator_get_state(orchestrator):
    """get_state() returns a dict with all expected keys."""
    state = orchestrator.get_state()

    assert isinstance(state, dict)
    expected_keys = {
        "task_id", "active_app", "browser_url", "browser_tab_title",
        "desktop_file_path", "open_files", "window_count",
        "windows", "checkpoint_count", "current_step",
    }
    assert set(state.keys()) == expected_keys
    assert state["task_id"] == "test-task-001"
    assert state["checkpoint_count"] == 0
    assert state["window_count"] == 0


def test_orchestrator_get_state_after_checkpoint(orchestrator):
    """get_state() reflects checkpoint data after saving one."""
    # Mock browser/desktop sessions to None so save_checkpoint doesn't crash
    with patch.object(
        type(orchestrator), "browser_session", new_callable=PropertyMock, return_value=None
    ), patch.object(
        type(orchestrator), "desktop_session", new_callable=PropertyMock, return_value=None
    ):
        orchestrator.save_checkpoint(
            step="test-step",
            active_app="notepad",
            browser_url="https://example.com",
        )

    state = orchestrator.get_state()
    assert state["current_step"] == "test-step"
    assert state["checkpoint_count"] == 1


# ---------------------------------------------------------------------------
# 5. test_save_checkpoint
# ---------------------------------------------------------------------------

def test_save_checkpoint(orchestrator):
    """Save a checkpoint and verify it appears in the checkpoints list."""
    with patch.object(
        type(orchestrator), "browser_session", new_callable=PropertyMock, return_value=None
    ), patch.object(
        type(orchestrator), "desktop_session", new_callable=PropertyMock, return_value=None
    ):
        cp = orchestrator.save_checkpoint(
            step="initial",
            active_app="browser",
            browser_url="https://google.com",
        )

    assert isinstance(cp, WorkflowCheckpoint)
    assert cp.step == "initial"
    assert cp.active_app == "browser"
    assert cp.browser_url == "https://google.com"
    assert len(orchestrator._checkpoints) == 1
    assert orchestrator._current_checkpoint is cp


def test_save_checkpoint_inherits_open_files(orchestrator):
    """A second checkpoint inherits open_files from the previous one."""
    with patch.object(
        type(orchestrator), "browser_session", new_callable=PropertyMock, return_value=None
    ), patch.object(
        type(orchestrator), "desktop_session", new_callable=PropertyMock, return_value=None
    ):
        cp1 = orchestrator.save_checkpoint(
            step="step-1",
            open_files=["/tmp/a.txt"],
        )
        cp2 = orchestrator.save_checkpoint(
            step="step-2",
            desktop_file_path="/tmp/b.txt",
        )

    # cp2 should have both files
    assert "/tmp/a.txt" in cp2.open_files
    assert "/tmp/b.txt" in cp2.open_files


# ---------------------------------------------------------------------------
# 6. test_transfer_file_to_desktop_file_not_found
# ---------------------------------------------------------------------------

def test_transfer_file_to_desktop_file_not_found(orchestrator):
    """Transferring a nonexistent file should return an error ToolOutput."""
    result = orchestrator.transfer_file_to_desktop("/nonexistent/path/file.txt")

    assert isinstance(result, ToolOutput)
    assert result.success is False
    assert "not found" in result.error.lower() or "File not found" in result.error


# ---------------------------------------------------------------------------
# 7. test_switch_to_app_not_found
# ---------------------------------------------------------------------------

def test_switch_to_app_not_found(orchestrator):
    """Switching to a nonexistent app should return a failure ToolOutput."""
    # Mock _launch_app to return False (app can't be launched)
    with patch.object(MultiAppOrchestrator, "_launch_app", return_value=False):
        result = orchestrator.switch_to_app("NonexistentApp999")

    assert isinstance(result, ToolOutput)
    assert result.success is False
    assert result.error is not None


def test_switch_to_app_existing_window(orchestrator):
    """Switching to an already-registered app should succeed via ensure_focus."""
    # Register a window in the registry
    ref = orchestrator.window_registry.register(title="MyApp Window")

    # Mock ensure_focus to return True
    with patch.object(
        orchestrator.window_registry, "ensure_focus", return_value=True
    ), patch.object(
        type(orchestrator), "browser_session", new_callable=PropertyMock, return_value=None
    ), patch.object(
        type(orchestrator), "desktop_session", new_callable=PropertyMock, return_value=None
    ):
        result = orchestrator.switch_to_app("MyApp")

    assert isinstance(result, ToolOutput)
    assert result.success is True
    assert result.result["window_ref_id"] == ref.ref_id


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

def test_orchestrator_window_registry_lazy_init():
    """window_registry property lazily initializes a WindowRegistry."""
    orch = MultiAppOrchestrator(task_id="lazy-test")
    assert orch._window_registry is None

    # Accessing the property should create one
    with patch.object(WindowRegistry, "__init__", lambda self: None):
        reg = orch.window_registry
        assert isinstance(reg, WindowRegistry)


def test_restore_from_checkpoint_no_checkpoint(orchestrator):
    """restore_from_checkpoint returns None when no checkpoint exists."""
    result = orchestrator.restore_from_checkpoint()
    assert result is None


def test_get_state_no_checkpoint(orchestrator):
    """get_state() works correctly when no checkpoint has been saved yet."""
    state = orchestrator.get_state()
    assert state["active_app"] is None
    assert state["current_step"] is None
    assert state["open_files"] == []


def test_launch_app_failure():
    """_launch_app returns False when subprocess raises."""
    with patch("core.environments.multi_app_orchestrator.subprocess.Popen", side_effect=OSError("fail")):
        result = MultiAppOrchestrator._launch_app("nonexistent_app_xyz")
        assert result is False


def test_launch_app_success_windows():
    """_launch_app returns True on Windows when subprocess.Popen succeeds."""
    with patch("core.environments.multi_app_orchestrator.sys") as mock_sys, \
         patch("core.environments.multi_app_orchestrator.subprocess.Popen") as mock_popen:
        mock_sys.platform = "win32"
        mock_popen.return_value = MagicMock()
        result = MultiAppOrchestrator._launch_app("notepad")
        assert result is True


def test_transfer_file_to_desktop_with_existing_file(orchestrator):
    """transfer_file_to_desktop with a real file should attempt to open it."""
    # Create a temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello")
        tmp_path = f.name

    try:
        # Mock subprocess.Popen and os.startfile to avoid actually opening
        with patch("core.environments.multi_app_orchestrator.subprocess.Popen") as mock_popen, \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.abspath", return_value=tmp_path), \
             patch.object(orchestrator, "_wait_for_window", return_value=None), \
             patch.object(
                 type(orchestrator), "browser_session", new_callable=PropertyMock, return_value=None
             ), patch.object(
                 type(orchestrator), "desktop_session", new_callable=PropertyMock, return_value=None
             ):
            # On Windows, os.startfile is used; on other platforms, subprocess.Popen
            if sys.platform == "win32":
                with patch("os.startfile"):
                    result = orchestrator.transfer_file_to_desktop(tmp_path)
            else:
                mock_popen.return_value = MagicMock()
                result = orchestrator.transfer_file_to_desktop(tmp_path)

        assert isinstance(result, ToolOutput)
        # Should succeed (file exists, app launch attempted)
        assert result.success is True
    finally:
        os.unlink(tmp_path)
