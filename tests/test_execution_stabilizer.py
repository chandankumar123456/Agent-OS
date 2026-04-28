import pytest
import os
import tempfile
import random
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from app.environments.execution_stabilizer import (
    ActionStabilizer,
    StabilizerConfig,
    ActionSnapshot,
)


@pytest.fixture
def stabilizer():
    return ActionStabilizer(StabilizerConfig())


@pytest.fixture
def mock_screenshots():
    """Create two identical and one different temp screenshots."""
    paths = []
    for i, color in enumerate([(255, 0, 0), (255, 0, 0), (0, 255, 0)]):
        path = os.path.join(tempfile.gettempdir(), f"mock_sc_{i}.png")
        img = Image.new("RGB", (100, 100), color)
        img.save(path)
        paths.append(path)
    yield paths
    for p in paths:
        if os.path.exists(p):
            os.remove(p)


@pytest.mark.asyncio
async def test_wait_for_ui_stability_stable_immediately(stabilizer, mock_screenshots):
    """If screenshots don't change, stability is detected quickly."""
    call_count = 0

    async def screenshot_fn(path):
        nonlocal call_count
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(path)
        call_count += 1
        return MagicMock(success=True)

    stable, path = await stabilizer.wait_for_ui_stability(
        screenshot_fn, max_wait=1.0, poll_interval=0.05
    )
    assert stable is True


@pytest.mark.asyncio
async def test_wait_for_ui_stability_timeout_on_constant_change(stabilizer):
    """If screenshots always change, timeout returns unstable."""

    async def screenshot_fn(path):
        img = Image.new("RGB", (100, 100))
        pixels = img.load()
        for i in range(100):
            for j in range(100):
                pixels[i, j] = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
        img.save(path)
        return MagicMock(success=True)

    stable, path = await stabilizer.wait_for_ui_stability(
        screenshot_fn, max_wait=0.3, poll_interval=0.1
    )
    assert stable is False


@pytest.mark.asyncio
async def test_verify_state_change_detects_change(stabilizer, mock_screenshots):
    before = mock_screenshots[0]  # red

    call_count = 0

    async def screenshot_fn(path):
        nonlocal call_count
        img = Image.new("RGB", (100, 100), (0, 255, 0))
        img.save(path)
        call_count += 1
        return MagicMock(success=True)

    async def tree_hash_fn():
        return "hash_after" if call_count > 0 else "hash_before"

    result = await stabilizer.verify_state_change(
        before_screenshot_path=before,
        before_tree_hash="hash_before",
        screenshot_fn=screenshot_fn,
        tree_hash_fn=tree_hash_fn,
        timeout=0.5,
        poll_interval=0.1,
    )
    assert result["changed"] is True
    assert result["screenshot_changed"] == True


@pytest.mark.asyncio
async def test_verify_state_change_no_change(stabilizer, mock_screenshots):
    before = mock_screenshots[0]  # red

    async def screenshot_fn(path):
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(path)
        return MagicMock(success=True)

    async def tree_hash_fn():
        return "same_hash"

    result = await stabilizer.verify_state_change(
        before_screenshot_path=before,
        before_tree_hash="same_hash",
        screenshot_fn=screenshot_fn,
        tree_hash_fn=tree_hash_fn,
        timeout=0.3,
        poll_interval=0.1,
    )
    assert result["changed"] is False


@pytest.mark.asyncio
async def test_execute_with_retry_success_no_retry(stabilizer):
    action_fn = AsyncMock(return_value=MagicMock(success=True, result="ok"))
    screenshot_fn = AsyncMock(return_value=MagicMock(success=True))
    tree_hash_fn = AsyncMock(return_value="hash")
    window_list_fn = AsyncMock(return_value=[])
    element_map_fn = lambda: {}

    result, snapshot = await stabilizer.execute_with_retry(
        action_name="click",
        action_fn=action_fn,
        params={"x": 10, "y": 20},
        screenshot_fn=screenshot_fn,
        tree_hash_fn=tree_hash_fn,
        window_list_fn=window_list_fn,
        element_map_fn=element_map_fn,
        stabilize=False,
        verify=False,
    )
    assert action_fn.call_count == 1
    assert snapshot.retry_count == 0
    assert snapshot.error is None


@pytest.mark.asyncio
async def test_execute_with_retry_retries_on_failure(stabilizer):
    action_fn = AsyncMock(
        side_effect=[Exception("fail1"), MagicMock(success=True, result="ok")]
    )
    screenshot_fn = AsyncMock(return_value=MagicMock(success=True))
    tree_hash_fn = AsyncMock(return_value="hash")
    window_list_fn = AsyncMock(return_value=[])
    element_map_fn = lambda: {}

    result, snapshot = await stabilizer.execute_with_retry(
        action_name="click",
        action_fn=action_fn,
        params={"x": 10, "y": 20},
        screenshot_fn=screenshot_fn,
        tree_hash_fn=tree_hash_fn,
        window_list_fn=window_list_fn,
        element_map_fn=element_map_fn,
        stabilize=False,
        verify=False,
    )
    assert action_fn.call_count == 2
    assert snapshot.retry_count == 1
    assert snapshot.error is None


@pytest.mark.asyncio
async def test_execute_with_retry_exhausts_retries(stabilizer):
    action_fn = AsyncMock(side_effect=Exception("always fails"))
    screenshot_fn = AsyncMock(return_value=MagicMock(success=True))
    tree_hash_fn = AsyncMock(return_value="hash")
    window_list_fn = AsyncMock(return_value=[])
    element_map_fn = lambda: {}

    result, snapshot = await stabilizer.execute_with_retry(
        action_name="click",
        action_fn=action_fn,
        params={"x": 10, "y": 20},
        screenshot_fn=screenshot_fn,
        tree_hash_fn=tree_hash_fn,
        window_list_fn=window_list_fn,
        element_map_fn=element_map_fn,
        stabilize=False,
        verify=False,
    )
    assert action_fn.call_count == 3  # initial + 2 retries
    assert snapshot.retry_count == 2
    assert snapshot.error is not None


@pytest.mark.asyncio
async def test_detect_popup_window_detects_save_dialog(stabilizer):
    async def window_list_fn():
        return [
            {"title": "MyApp - Main", "class_name": "MainWindow"},
            {"title": "Save As", "class_name": "#32770"},
        ]

    popup = await stabilizer.detect_popup_window(window_list_fn)
    assert popup is not None
    assert popup["title"] == "Save As"


@pytest.mark.asyncio
async def test_detect_popup_window_no_popup(stabilizer):
    async def window_list_fn():
        return [
            {"title": "MyApp - Main", "class_name": "MainWindow"},
        ]

    popup = await stabilizer.detect_popup_window(window_list_fn)
    assert popup is None


def test_snapshot_history_capped(stabilizer):
    for i in range(55):
        s = ActionSnapshot(
            timestamp="",
            action_name="click",
            params={},
            before_screenshot_path=None,
            after_screenshot_path=None,
            before_tree_hash=None,
            after_tree_hash=None,
            before_element_map={},
            selected_target=None,
        )
        stabilizer.add_snapshot(s)
    assert len(stabilizer.get_snapshot_history()) == 50
