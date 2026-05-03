import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from app.environments.desktop_env import DesktopSession, DesktopSessionManager
from app.environments.execution_stabilizer import ActionStabilizer


@pytest.fixture
def mock_pyautogui():
    with patch("app.environments.desktop_env.pyautogui") as m:
        size_mock = MagicMock()
        size_mock.width = 1920
        size_mock.height = 1080
        m.size.return_value = size_mock
        yield m


@pytest.fixture
def mock_pyperclip():
    with patch("app.environments.desktop_env.pyperclip") as m:
        yield m


@pytest.fixture
def mock_mss():
    with patch("app.environments.desktop_env.mss") as m:
        sct_instance = MagicMock()
        # mss.MSS() is called in the code, so mock MSS attribute's return value
        mss_mock = MagicMock()
        mss_mock.__enter__ = MagicMock(return_value=sct_instance)
        mss_mock.__exit__ = MagicMock(return_value=False)
        m.MSS = MagicMock(return_value=mss_mock)
        yield m, sct_instance


@pytest.fixture
def mock_gw():
    with patch("app.environments.desktop_env.gw") as m:
        yield m


@pytest.fixture
def manager():
    return DesktopSessionManager()


@pytest.fixture(autouse=True)
def mock_sync_wait():
    async def _noop(self, action_name="generic", timeout=None, poll_interval=None):
        pass

    with patch.object(DesktopSession, "_sync_wait", _noop):
        yield


@pytest.fixture(autouse=True)
def mock_stabilizer_extras():
    """Make stabilizer fast and deterministic in unit tests."""
    with patch.object(
        ActionStabilizer, "detect_popup_window", new=AsyncMock(return_value=None)
    ):
        with patch.object(
            ActionStabilizer,
            "verify_state_change",
            new=AsyncMock(
                return_value={
                    "changed": True,
                    "screenshot_changed": True,
                    "tree_changed": False,
                    "after_screenshot_path": None,
                    "after_tree_hash": None,
                    "notes": "mocked change",
                }
            ),
        ):
            yield


class TestDesktopSession:
    @pytest.mark.asyncio
    async def test_session_creation_and_reuse(self, manager, mock_pyautogui):
        s1 = await manager.get_or_create_session("task-1")
        s2 = await manager.get_or_create_session("task-1")
        assert s1 is s2
        assert s1.task_id == "task-1"

    @pytest.mark.asyncio
    async def test_screenshot_success(self, mock_pyautogui, mock_mss):
        _, sct_instance = mock_mss
        session = DesktopSession("task-sc")
        result = await session.screenshot(path="/tmp/test.png")
        assert result.success is True
        assert "/tmp/test.png" in str(result.result)
        sct_instance.shot.assert_called_once_with(output="/tmp/test.png")

    @pytest.mark.asyncio
    async def test_screenshot_failure(self, mock_pyautogui, mock_mss):
        _, sct_instance = mock_mss
        sct_instance.shot.side_effect = Exception("mss error")
        session = DesktopSession("task-sc2")
        result = await session.screenshot(path="/tmp/test.png")
        assert result.success is False
        assert "mss error" in result.error

    @pytest.mark.asyncio
    async def test_click_safety_bounds(self, mock_pyautogui):
        session = DesktopSession("task-click")
        result = await session.click(100, 200)
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(100, 200)

        result = await session.click(2000, 2000)
        assert result.success is False
        assert "out of screen bounds" in result.error

    @pytest.mark.asyncio
    async def test_type_text(self, mock_pyautogui):
        session = DesktopSession("task-type")
        result = await session.type_text("hello", interval=0.05)
        assert result.success is True
        mock_pyautogui.typewrite.assert_called_once_with("hello", interval=0.05)

    @pytest.mark.asyncio
    async def test_type_text_skips_sync_wait_for_deterministic_text_apps(self, mock_pyautogui):
        session = DesktopSession("task-type-fast")
        session._last_opened_app_name = "notepad"
        session._sync_wait = AsyncMock()
        with patch.object(session, "_get_active_window_title", return_value=None):
            result = await session.type_text("hello", interval=0.05)
        assert result.success is True
        session._sync_wait.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_type_text_runs_sync_wait_for_non_deterministic_apps(self, mock_pyautogui):
        session = DesktopSession("task-type-slow")
        session._last_opened_app_name = "excel"
        session._sync_wait = AsyncMock()
        with patch.object(session, "_get_active_window_title", return_value=None):
            result = await session.type_text("hello", interval=0.05)
        assert result.success is True
        session._sync_wait.assert_awaited_once_with(action_name="type_text")

    @pytest.mark.asyncio
    async def test_press_key_single(self, mock_pyautogui):
        session = DesktopSession("task-key")
        result = await session.press_key("enter")
        assert result.success is True
        mock_pyautogui.press.assert_called_once_with("enter")

    @pytest.mark.asyncio
    async def test_press_key_hotkey(self, mock_pyautogui):
        session = DesktopSession("task-hotkey")
        result = await session.press_key("ctrl+c")
        assert result.success is True
        mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")

    @pytest.mark.asyncio
    async def test_clipboard_get_set(self, mock_pyautogui, mock_pyperclip):
        session = DesktopSession("task-clip")
        mock_pyperclip.paste.return_value = "copied text"
        result = await session.get_clipboard()
        assert result.success is True
        assert result.result == "copied text"

        result = await session.set_clipboard("new text")
        assert result.success is True
        mock_pyperclip.copy.assert_called_once_with("new text")

    @pytest.mark.asyncio
    async def test_window_list_windows(self, mock_pyautogui, mock_gw):
        with patch.object(sys, "platform", "win32"):
            win = MagicMock()
            win.title = "Notepad"
            type(win).left = PropertyMock(return_value=10)
            type(win).top = PropertyMock(return_value=20)
            type(win).width = PropertyMock(return_value=300)
            type(win).height = PropertyMock(return_value=400)
            mock_gw.getAllWindows.return_value = [win]
            session = DesktopSession("task-win")
            result = await session.get_window_list()
            assert result.success is True
            assert result.result["count"] == 1
            assert result.result["windows"][0]["title"] == "Notepad"

    @pytest.mark.asyncio
    async def test_window_list_linux(self, mock_pyautogui):
        with patch.object(sys, "platform", "linux"):
            with patch("app.environments.desktop_env.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="0 1 hostname Terminal\n")
                session = DesktopSession("task-lin")
                with patch.object(session, "_is_headless", return_value=False):
                    result = await session.get_window_list()
                    assert result.success is True
                    assert result.result["count"] == 1
                    assert result.result["windows"][0]["title"] == "Terminal"

    @pytest.mark.asyncio
    async def test_focus_window_not_found(self, mock_pyautogui, mock_gw):
        with patch.object(sys, "platform", "win32"):
            mock_gw.getWindowsWithTitle.return_value = []
            session = DesktopSession("task-focus")
            result = await session.focus_window("DoesNotExist")
            assert result.success is False
            assert "No window found" in result.error

    @pytest.mark.asyncio
    async def test_graceful_headless_failure(self):
        session = DesktopSession("task-headless")
        with patch.object(session, "_is_headless", return_value=True):
            result = await session.click(10, 10)
            assert result.success is False
            assert "headless" in result.error.lower()

    @pytest.mark.asyncio
    async def test_close_session(self, manager, mock_pyautogui):
        await manager.get_or_create_session("task-close")
        result = await manager.close_session("task-close")
        assert result.success is True
        assert manager.get_session("task-close") is None

    @pytest.mark.asyncio
    async def test_get_mouse_position(self, mock_pyautogui):
        pos_mock = MagicMock()
        pos_mock.x = 100
        pos_mock.y = 200
        mock_pyautogui.position.return_value = pos_mock
        session = DesktopSession("task-mouse")
        result = await session.get_mouse_position()
        assert result.success is True
        assert result.result == {"x": 100, "y": 200}

    @pytest.mark.asyncio
    async def test_scroll(self, mock_pyautogui):
        session = DesktopSession("task-scroll")
        result = await session.scroll(-500)
        assert result.success is True
        mock_pyautogui.scroll.assert_called_once_with(-500)

    @pytest.mark.asyncio
    async def test_get_ui_tree_headless(self):
        session = DesktopSession("task-ui-headless")
        with patch.object(session, "_is_headless", return_value=True):
            result = await session.get_ui_tree()
            assert result.success is False
            assert "headless" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_element_not_found(self, mock_pyautogui):
        session = DesktopSession("task-click-missing")
        result = await session.click_element(999)
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_type_element_not_found(self, mock_pyautogui):
        session = DesktopSession("task-type-missing")
        result = await session.type_element(999, "hello")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_focus_and_interact_not_found(self, mock_pyautogui):
        session = DesktopSession("task-focus-missing")
        result = await session.focus_and_interact(999, "enter")
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_click_element_success(self, mock_pyautogui):
        session = DesktopSession("task-click-ok")
        session._ui_element_map[1] = {
            "center": (100, 200),
            "name": "Submit",
            "type": "Button",
        }
        result = await session.click_element(1)
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(100, 200)

    @pytest.mark.asyncio
    async def test_type_element_success(self, mock_pyautogui):
        session = DesktopSession("task-type-ok")
        session._ui_element_map[2] = {
            "center": (150, 250),
            "name": "SearchBox",
            "type": "Edit",
        }
        result = await session.type_element(2, "query")
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(150, 250)
        mock_pyautogui.typewrite.assert_called_once_with("query", interval=0.01)

    @pytest.mark.asyncio
    async def test_focus_and_interact_success(self, mock_pyautogui):
        session = DesktopSession("task-focus-ok")
        session._ui_element_map[3] = {
            "center": (50, 50),
            "name": "OK",
            "type": "Button",
        }
        result = await session.focus_and_interact(3, "enter")
        assert result.success is True
        mock_pyautogui.press.assert_called_once_with("enter")

    @pytest.mark.asyncio
    async def test_element_map_cleared_on_get_ui_tree(self, mock_mss):
        session = DesktopSession("task-clear")
        session._ui_element_map = {1: {"name": "dummy"}, 2: {"name": "dummy2"}}
        session._next_element_id = 99
        with patch.object(session, "_build_ui_tree_windows", new_callable=AsyncMock) as mock_build:
            mock_build.return_value = []
            with patch.object(sys, "platform", "win32"):
                with patch.object(session, "_is_headless", return_value=False):
                    await session.get_ui_tree()
                    assert session._ui_element_map == {}
                    assert session._next_element_id == 1

    @pytest.mark.asyncio
    async def test_click_element_creates_snapshot(self, mock_pyautogui):
        session = DesktopSession("task-snap")
        session._ui_element_map[1] = {
            "center": (100, 200),
            "name": "Submit",
            "type": "Button",
        }
        result = await session.click_element(1)
        assert result.success is True
        history = session.get_snapshot_history()
        assert len(history) == 1
        assert history[0]["action_name"] == "click_element"
        assert history[0]["params"]["element_id"] == 1

    @pytest.mark.asyncio
    async def test_snapshot_history_cleared_on_close(self, mock_pyautogui):
        session = DesktopSession("task-snap-close")
        session._ui_element_map[1] = {"center": (10, 20), "name": "A", "type": "Button"}
        await session.click_element(1)
        assert len(session.get_snapshot_history()) == 1
        await session.close()
        assert len(session.get_snapshot_history()) == 0

    @pytest.mark.asyncio
    async def test_desktop_session_caches_ui_tree(self):
        """FR8/NFR1: Tree should be cached and not rebuilt if hash unchanged and <5s old."""
        session = DesktopSession(task_id="cache-test")
        with patch.object(session, "_build_ui_tree_windows", new_callable=AsyncMock) as mock_build:
            mock_build.return_value = [
                {"id": 1, "name": "OK", "type": "Button"},
                {"id": 2, "name": "Cancel", "type": "Button"},
            ]
            with patch.object(session, "_is_headless", return_value=False):
                with patch.object(sys, "platform", "win32"):
                    tree1 = await session.get_ui_tree()
                    tree2 = await session.get_ui_tree()
                    assert tree1.success is True
                    assert tree2.success is True
                    assert tree1.result == tree2.result
                    assert tree1.result.get("perception_layer") == "uia"
                    mock_build.assert_awaited_once()  # Should only build once
