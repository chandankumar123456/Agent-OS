import pytest
import os
import tempfile
import random
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from core.environments.execution_stabilizer import (
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


# ── New tests for enhanced stabilization ──────────────────────────────

class TestActionSpecificConfig:
    def test_get_for_action_override(self):
        config = StabilizerConfig()
        click_config = config.get_for_action("click")
        assert click_config.stabilization_max_wait == 2.0
        assert click_config.verification_timeout == 2.0

    def test_get_for_action_default(self):
        config = StabilizerConfig()
        generic_config = config.get_for_action("unknown_action")
        assert generic_config.stabilization_max_wait == 3.0
        assert generic_config.verification_timeout == 3.0

    def test_open_application_config(self):
        config = StabilizerConfig()
        app_config = config.get_for_action("open_application")
        assert app_config.stabilization_max_wait == 5.0
        assert app_config.verification_timeout == 8.0


class TestWindowStabilization:
    @pytest.mark.asyncio
    async def test_wait_for_window_stability_stable(self):
        stabilizer = ActionStabilizer(StabilizerConfig())
        call_count = 0

        async def window_list_fn():
            nonlocal call_count
            call_count += 1
            return [{"title": "Window1"}, {"title": "Window2"}]

        stable, windows = await stabilizer.wait_for_window_stability(
            window_list_fn, max_wait=1.0, poll_interval=0.05
        )
        assert stable is True
        assert len(windows) == 2

    @pytest.mark.asyncio
    async def test_wait_for_window_stability_unstable(self):
        stabilizer = ActionStabilizer(StabilizerConfig())
        call_count = 0

        async def window_list_fn():
            nonlocal call_count
            call_count += 1
            # Return different windows each time
            return [{"title": f"Window{call_count}"}]

        stable, windows = await stabilizer.wait_for_window_stability(
            window_list_fn, max_wait=0.3, poll_interval=0.1
        )
        assert stable is False


class TestTreeStabilization:
    @pytest.mark.asyncio
    async def test_wait_for_tree_stability_stable(self):
        stabilizer = ActionStabilizer(StabilizerConfig())

        async def tree_hash_fn():
            return "stable_hash"

        stable, hash_val = await stabilizer.wait_for_tree_stability(
            tree_hash_fn, max_wait=1.0, poll_interval=0.05
        )
        assert stable is True
        assert hash_val == "stable_hash"

    @pytest.mark.asyncio
    async def test_wait_for_tree_stability_unstable(self):
        stabilizer = ActionStabilizer(StabilizerConfig())
        call_count = 0

        async def tree_hash_fn():
            nonlocal call_count
            call_count += 1
            return f"hash_{call_count}"

        stable, hash_val = await stabilizer.wait_for_tree_stability(
            tree_hash_fn, max_wait=0.3, poll_interval=0.1
        )
        assert stable is False


class TestSemanticVerification:
    @pytest.mark.asyncio
    async def test_verify_expected_state_passes(self):
        stabilizer = ActionStabilizer(StabilizerConfig())

        async def expected_state_fn():
            return True, "Window found"

        result = await stabilizer.verify_expected_state(
            expected_state_fn, timeout=0.5, poll_interval=0.1
        )
        assert result["passed"] is True
        assert result["notes"] == "Window found"

    @pytest.mark.asyncio
    async def test_verify_expected_state_fails(self):
        stabilizer = ActionStabilizer(StabilizerConfig())

        async def expected_state_fn():
            return False, "Window not found"

        result = await stabilizer.verify_expected_state(
            expected_state_fn, timeout=0.3, poll_interval=0.1
        )
        assert result["passed"] is False


class TestActionTruthLogging:
    @pytest.mark.asyncio
    async def test_execute_with_retry_expected_state_fn(self, stabilizer):
        action_fn = AsyncMock(return_value=MagicMock(success=True, result="ok"))
        screenshot_fn = AsyncMock(return_value=MagicMock(success=True))
        tree_hash_fn = AsyncMock(return_value="hash")
        window_list_fn = AsyncMock(return_value=[])
        element_map_fn = lambda: {}

        async def expected_state_fn():
            return True, "Notepad window visible"

        result, snapshot = await stabilizer.execute_with_retry(
            action_name="open_application",
            action_fn=action_fn,
            params={"app_name": "notepad"},
            screenshot_fn=screenshot_fn,
            tree_hash_fn=tree_hash_fn,
            window_list_fn=window_list_fn,
            element_map_fn=element_map_fn,
            stabilize=False,
            verify=False,
            expected_state_fn=expected_state_fn,
        )
        assert result.success is True
        assert snapshot.semantic_verified is True
        assert snapshot.semantic_notes == "Notepad window visible"
        assert snapshot.expected_outcome == "expected_state_fn"

    @pytest.mark.asyncio
    async def test_execute_with_retry_semantic_fail_retries(self, stabilizer):
        action_fn = AsyncMock(return_value=MagicMock(success=True, result="ok"))
        screenshot_fn = AsyncMock(return_value=MagicMock(success=True))
        tree_hash_fn = AsyncMock(return_value="hash")
        window_list_fn = AsyncMock(return_value=[])
        element_map_fn = lambda: {}

        call_count = 0

        async def expected_state_fn():
            nonlocal call_count
            call_count += 1
            return call_count > 1, "Window appeared"

        result, snapshot = await stabilizer.execute_with_retry(
            action_name="open_application",
            action_fn=action_fn,
            params={"app_name": "notepad"},
            screenshot_fn=screenshot_fn,
            tree_hash_fn=tree_hash_fn,
            window_list_fn=window_list_fn,
            element_map_fn=element_map_fn,
            stabilize=False,
            verify=False,
            expected_state_fn=expected_state_fn,
        )
        assert result.success is True
        assert snapshot.semantic_verified is True
        assert call_count == 2  # First failed, second passed

    @pytest.mark.asyncio
    async def test_execute_with_retry_semantic_exhausted(self, stabilizer):
        action_fn = AsyncMock(return_value=MagicMock(success=True, result="ok"))
        screenshot_fn = AsyncMock(return_value=MagicMock(success=True))
        tree_hash_fn = AsyncMock(return_value="hash")
        window_list_fn = AsyncMock(return_value=[])
        element_map_fn = lambda: {}

        async def expected_state_fn():
            return False, "Window never appeared"

        result, snapshot = await stabilizer.execute_with_retry(
            action_name="open_application",
            action_fn=action_fn,
            params={"app_name": "notepad"},
            screenshot_fn=screenshot_fn,
            tree_hash_fn=tree_hash_fn,
            window_list_fn=window_list_fn,
            element_map_fn=element_map_fn,
            stabilize=False,
            verify=False,
            expected_state_fn=expected_state_fn,
        )
        # Should exhaust retries and return with semantic_verified=False
        assert snapshot.semantic_verified is False
        assert snapshot.semantic_notes is not None

    def test_log_action_truth(self, stabilizer, caplog):
        import logging

        snapshot = ActionSnapshot(
            timestamp="2024-01-01T00:00:00",
            action_name="click",
            params={"x": 10, "y": 20},
            before_screenshot_path=None,
            after_screenshot_path=None,
            before_tree_hash=None,
            after_tree_hash=None,
            before_element_map={},
            selected_target=None,
            verification_result={"changed": True},
            semantic_verified=True,
            semantic_notes="Button clicked",
            retry_count=0,
        )
        with caplog.at_level(logging.INFO):
            stabilizer._log_action_truth(snapshot, MagicMock(success=True), "SUCCESS")

        assert "ACTION=click" in caplog.text
        assert "STATUS=SUCCESS" in caplog.text
        assert "RETRY=0" in caplog.text


@pytest.mark.asyncio
async def test_stabilizer_detects_infinite_loop():
    """RR4: Must detect same action on same element failing 3x with no state change and abort."""
    from core.environments.execution_stabilizer import ActionStabilizer, StabilizerConfig
    stab = ActionStabilizer(config=StabilizerConfig())
    for i in range(3):
        stab.add_snapshot(
            ActionSnapshot(
                timestamp="",
                action_name="click",
                params={"element_id": 7},
                before_screenshot_path=None,
                after_screenshot_path=None,
                before_tree_hash=None,
                after_tree_hash=None,
                before_element_map={},
                selected_target=None,
                verification_result={"changed": False},
            )
        )
    with pytest.raises(RuntimeError, match="infinite loop"):
        stab.detect_infinite_loop()


def test_stabilizer_config_has_cleanup_age():
    """FR5.3: StabilizerConfig must expose temp_screenshot_max_age_seconds."""
    from core.environments.execution_stabilizer import StabilizerConfig
    cfg = StabilizerConfig(temp_screenshot_max_age_seconds=120)
    assert cfg.temp_screenshot_max_age_seconds == 120


@pytest.mark.asyncio
async def test_dismiss_popup_verifies_popup_is_gone():
    """NFR3: dismiss_popup must confirm popup no longer exists after dismissal."""
    from core.environments.execution_stabilizer import ActionStabilizer
    from unittest.mock import patch, AsyncMock
    stab = ActionStabilizer()

    # First call (before first strategy) detects popup, second call (after dismissal) does not
    with patch.object(stab, "detect_popup_window", new_callable=AsyncMock, side_effect=[
        {"title": "Popup"},  # pre-dismissal check: popup found
        None,                 # post-dismissal check: popup gone
    ]) as mock_detect:
        result = await stab.dismiss_popup(
            screenshot_fn=AsyncMock(),
            click_fn=AsyncMock(),
            press_key_fn=AsyncMock(),
            window_list_fn=AsyncMock(),
        )
    assert result["dismissed"] is True
    assert mock_detect.await_count >= 2
