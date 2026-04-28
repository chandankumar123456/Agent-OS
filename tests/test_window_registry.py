"""Tests for WindowRef dataclass and WindowRegistry class.

Phase 5: Validates registration, lookup, find-by-title, stale marking,
serialization, active-window detection, and refresh — all in a headless
environment with OS-specific modules mocked out.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

from app.environments.window_registry import WindowRef, WindowRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """Return a fresh WindowRegistry with OS-level calls mocked out."""
    with patch.object(WindowRegistry, "__init__", lambda self: None):
        reg = WindowRegistry.__new__(WindowRegistry)
        # Manually set what __init__ would set
        reg._registry = {}
        reg._logger = MagicMock()
        return reg


# ---------------------------------------------------------------------------
# 1. test_register_window
# ---------------------------------------------------------------------------

def test_register_window(registry):
    """Register a window by title and verify it gets a ref_id."""
    ref = registry.register(title="Notepad")

    assert ref is not None
    assert isinstance(ref, WindowRef)
    assert ref.ref_id, "ref_id should be non-empty"
    assert ref.title == "Notepad"
    assert ref.is_alive is True
    assert ref in registry._registry.values()


# ---------------------------------------------------------------------------
# 2. test_lookup_by_ref_id
# ---------------------------------------------------------------------------

def test_lookup_by_ref_id(registry):
    """Register a window then look it up by ref_id."""
    ref = registry.register(title="Calculator")
    found = registry.lookup(ref.ref_id)

    assert found is not None
    assert found.ref_id == ref.ref_id
    assert found.title == "Calculator"


def test_lookup_by_ref_id_not_found(registry):
    """Looking up a nonexistent ref_id returns None."""
    assert registry.lookup("nonexistent_id") is None


# ---------------------------------------------------------------------------
# 3. test_find_by_title
# ---------------------------------------------------------------------------

def test_find_by_title(registry):
    """find_by_title uses case-insensitive substring match."""
    registry.register(title="Untitled - Notepad")
    result = registry.find_by_title("Note")

    assert result is not None
    assert "Note" in result.title


def test_find_by_title_exact_match(registry):
    """find_by_title works with an exact title match."""
    registry.register(title="Notepad")
    result = registry.find_by_title("Notepad")

    assert result is not None
    assert result.title == "Notepad"


# ---------------------------------------------------------------------------
# 4. test_find_by_title_no_match
# ---------------------------------------------------------------------------

def test_find_by_title_no_match(registry):
    """find_by_title returns None when no title matches."""
    registry.register(title="Notepad")
    result = registry.find_by_title("Photoshop")

    assert result is None


# ---------------------------------------------------------------------------
# 5. test_mark_stale_and_recover
# ---------------------------------------------------------------------------

def test_mark_stale_and_recover(registry):
    """Mark a window stale and verify is_alive becomes False."""
    ref = registry.register(title="Notepad")
    assert ref.is_alive is True

    registry.mark_stale(ref.ref_id)
    assert ref.is_alive is False


def test_mark_stale_nonexistent(registry):
    """Marking a nonexistent ref_id as stale should not raise."""
    # Should log a warning but not crash
    registry.mark_stale("does_not_exist")


# ---------------------------------------------------------------------------
# 6. test_serialization_round_trip
# ---------------------------------------------------------------------------

def test_serialization_round_trip(registry):
    """Register a window, serialize to dict, deserialize, verify same data."""
    ref = registry.register(title="VSCode", hwnd=12345, pid=999)

    # WindowRef round-trip
    ref_dict = ref.to_dict()
    restored_ref = WindowRef.from_dict(ref_dict)

    assert restored_ref.ref_id == ref.ref_id
    assert restored_ref.title == "VSCode"
    assert restored_ref.hwnd == 12345
    assert restored_ref.pid == 999


def test_registry_serialization_round_trip(registry):
    """Full registry to_dict / from_dict round-trip."""
    registry.register(title="App1")
    registry.register(title="App2")

    data = registry.to_dict()
    restored = WindowRegistry.from_dict(data)

    assert len(restored._registry) == 2
    # Verify titles survived the round-trip
    titles = {r.title for r in restored._registry.values()}
    assert titles == {"App1", "App2"}


# ---------------------------------------------------------------------------
# 7. test_get_active_window
# ---------------------------------------------------------------------------

def test_get_active_window_headless(registry):
    """In a headless environment, get_active_window may return None — that's OK."""
    # Mock all OS-level detection to return nothing
    with patch("app.environments.window_registry._lazy_ctypes", return_value=None), \
         patch("app.environments.window_registry._lazy_pygetwindow", return_value=None), \
         patch("app.environments.window_registry._lazy_psutil", return_value=None):
        result = registry.get_active_window()
        # In headless, result can be None — we just verify no crash
        assert result is None or isinstance(result, WindowRef)


def test_get_active_window_with_mock_window(registry):
    """When pygetwindow reports an active window, it should be registered."""
    mock_gw = MagicMock()
    mock_win = MagicMock()
    mock_win.title = "ActiveApp"
    mock_win._hWnd = 42
    mock_gw.getActiveWindow.return_value = mock_win

    with patch("app.environments.window_registry._lazy_ctypes", return_value=None), \
         patch("app.environments.window_registry._lazy_pygetwindow", return_value=mock_gw), \
         patch("app.environments.window_registry._lazy_psutil", return_value=None):
        # Force non-Windows path so pygetwindow is used
        with patch("app.environments.window_registry.sys") as mock_sys:
            mock_sys.platform = "linux"
            result = registry.get_active_window()

    assert result is not None
    assert result.title == "ActiveApp"


# ---------------------------------------------------------------------------
# 8. test_refresh_updates_titles
# ---------------------------------------------------------------------------

def test_refresh_no_crash(registry):
    """Calling refresh() on a registry should not crash, even in headless."""
    registry.register(title="TestWindow")

    with patch("app.environments.window_registry._lazy_ctypes", return_value=None), \
         patch("app.environments.window_registry._lazy_pygetwindow", return_value=None), \
         patch("app.environments.window_registry._lazy_psutil", return_value=None):
        # refresh should not raise
        changed = registry.refresh()

    # In headless, the window will be marked stale (no OS confirmation)
    assert isinstance(changed, list)


def test_refresh_marks_stale_when_unreachable(registry):
    """When no OS module can confirm a window, refresh should mark it stale."""
    ref = registry.register(title="GhostWindow")

    with patch("app.environments.window_registry._lazy_ctypes", return_value=None), \
         patch("app.environments.window_registry._lazy_pygetwindow", return_value=None), \
         patch("app.environments.window_registry._lazy_psutil", return_value=None):
        changed = registry.refresh()

    # Window should be marked stale since nothing can verify it
    assert ref.is_alive is False
    assert ref in changed


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

def test_find_by_pid(registry):
    """find_by_pid locates a window by its process ID."""
    registry.register(title="AppByPID", pid=1234)
    result = registry.find_by_pid(1234)

    assert result is not None
    assert result.pid == 1234
    assert result.title == "AppByPID"


def test_find_by_pid_no_match(registry):
    """find_by_pid returns None for unknown PID."""
    registry.register(title="AppByPID", pid=1234)
    assert registry.find_by_pid(5678) is None


def test_register_with_patterns(registry):
    """title_patterns should include the title by default."""
    ref = registry.register(title="Chrome", title_patterns=["Google Chrome", "Chromium"])

    assert "Chrome" in ref.title_patterns
    assert "Google Chrome" in ref.title_patterns
    assert "Chromium" in ref.title_patterns


def test_find_by_pattern_regex(registry):
    """find_by_pattern supports regex patterns."""
    registry.register(title="Google Chrome - Search")
    results = registry.find_by_pattern(r"Chrome|Firefox")

    assert len(results) >= 1
    assert results[0].title == "Google Chrome - Search"


def test_find_by_pattern_substring(registry):
    """find_by_pattern falls back to substring match for invalid regex."""
    # Use a title that literally contains an unclosed bracket so the
    # invalid-regex pattern is also a substring of the title.
    registry.register(title="Report [Draft")
    # "[Draft" is an invalid regex (unclosed bracket) AND a substring of the title
    results = registry.find_by_pattern("[Draft")

    # Should fall back to substring match
    assert len(results) >= 1
    assert "Draft" in results[0].title


def test_window_ref_from_dict_ignores_extra_keys():
    """from_dict should silently ignore keys not in the dataclass."""
    data = {
        "ref_id": "abc123",
        "title": "Test",
        "extra_key": "should_be_ignored",
    }
    ref = WindowRef.from_dict(data)
    assert ref.ref_id == "abc123"
    assert ref.title == "Test"
    assert not hasattr(ref, "extra_key") or getattr(ref, "extra_key", None) is None