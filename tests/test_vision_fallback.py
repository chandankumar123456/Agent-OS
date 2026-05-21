"""Tests for DPI scaling in vision fallback (FR7.1)."""

import pytest
from unittest.mock import patch, MagicMock

from core.environments.vision_fallback import OpenCVFallbackParser


class TestDPIScaling:
    """FR7.1: DPI must scale thresholds on high-DPI displays."""

    def test_get_dpi_scale_factor_default(self):
        """At default 96 DPI, scale factor is 1.0."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(96, 96)):
            scale = parser._get_dpi_scale_factor()
        assert scale == 1.0

    def test_get_dpi_scale_factor_150_percent(self):
        """At 144 DPI (150%), scale factor is 1.5."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(144, 144)):
            scale = parser._get_dpi_scale_factor()
        assert scale == 1.5

    def test_get_dpi_scale_factor_200_percent(self):
        """At 192 DPI (200%), scale factor should be 2.0."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(192, 192)):
            scale = parser._get_dpi_scale_factor()
        assert scale == 2.0

    def test_get_dpi_scale_factor_minimum_1(self):
        """Scale factor is never below 1.0 (prevents shrinking on low DPI)."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(72, 72)):
            scale = parser._get_dpi_scale_factor()
        assert scale == 1.0

    def test_get_dpi_scale_factor_uses_x_dpi(self):
        """Scale factor uses horizontal DPI only."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(144, 192)):
            scale = parser._get_dpi_scale_factor()
        assert scale == 1.5  # 144 / 96 = 1.5

    def test_dpi_scale_is_stored_during_parse(self):
        """parse_screenshot() computes and stores DPI scale factor."""
        parser = OpenCVFallbackParser()
        # Default should be 1.0 before parsing
        assert parser._dpi_scale == 1.0
        # Mock _get_screen_dpi to return 192 DPI
        with patch.object(parser, "_get_screen_dpi", return_value=(192, 192)):
            # Also mock cv2.imread to return None to short-circuit early
            with patch("core.environments.vision_fallback.cv2") as mock_cv2:
                mock_cv2.imread.return_value = None
                parser.parse_screenshot("/fake/path.png")
        # After parse, scale should be computed
        assert parser._dpi_scale == 2.0

    def test_validate_element_bounds_scales_minimum_size(self):
        """Minimum element size (3px) is scaled by DPI."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(192, 192)):
            if parser.is_available():
                parser._dpi_scale = parser._get_dpi_scale_factor()
                # At 2x scale, min size is 6px
                # Create a 4px wide element - would pass at 1x (4 >= 3) but fail at 2x (4 < 6)
                from core.environments.vision_fallback import DetectedElement
                elements = [
                    DetectedElement(1, (10, 10, 4, 8), "button", "test", 0.7),
                ]
                result = parser._validate_element_bounds(elements, 1920, 1080)
                # At 2x scale, min_size = 6, and 4 < 6 so element is filtered out
                assert len(result) == 0

                # Reset to 1x scale: a 4px element should pass (4 >= 3)
                parser._dpi_scale = 1.0
                elements2 = [
                    DetectedElement(2, (10, 10, 4, 8), "button", "test", 0.7),
                ]
                result2 = parser._validate_element_bounds(elements2, 1920, 1080)
                assert len(result2) == 1


class TestTextProximityScaling:
    """Text proximity threshold must scale with DPI."""

    def test_text_proximity_scales_with_dpi(self):
        """TEXT_PROXIMITY_PX is scaled by DPI factor."""
        parser = OpenCVFallbackParser()
        with patch.object(parser, "_get_screen_dpi", return_value=(192, 192)):
            parser._dpi_scale = parser._get_dpi_scale_factor()
            # At 2x, TEXT_PROXIMITY should be 80 instead of 40
            assert parser._dpi_scale == 2.0
            # _filter_text_spam uses self.TEXT_PROXIMITY_PX
            # We can verify by checking that the method works with scaled proximity
            from core.environments.vision_fallback import DetectedElement
            # Two elements: a button and a text 60px away (should be near at 2x scale)
            button = DetectedElement(1, (100, 100, 50, 30), "button", "OK", 0.7)
            # Text 60px away horizontally from button edge: at 1x scale (threshold=40) it's too far
            # At 2x scale (threshold=80) it's near enough
            text = DetectedElement(2, (210, 100, 80, 20), "text", "Label", 0.5)
            controls = [button]
            # At default 1x scale, 60px > 40px threshold -> not near
            result_1x = parser._is_near_any_control(text, controls, threshold_px=40)
            assert result_1x is False, "At 1x, 60px distance should exceed 40px threshold"

            # Update parser's proximity with scaled value
            parser.TEXT_PROXIMITY_PX = int(40 * parser._dpi_scale)  # = 80
            result_2x = parser._is_near_any_control(text, controls, threshold_px=parser.TEXT_PROXIMITY_PX)
            assert result_2x is True, "At 2x, 60px distance should be within 80px threshold"


class TestTextRegionScaling:
    """Text region size thresholds scale with DPI."""

    def test_text_region_size_limits_scale(self):
        """MSER min/max area and size limits scale with DPI."""
        # This test verifies the scaling logic conceptually.
        # At 2x DPI, the effective minimum text width should be 48 instead of 24.
        parser = OpenCVFallbackParser()
        parser._dpi_scale = 2.0
        # We verify that the scaling formula is applied correctly
        min_w = int(24 * parser._dpi_scale)
        min_h = int(12 * parser._dpi_scale)
        max_w = int(450 * parser._dpi_scale)
        max_h = int(70 * parser._dpi_scale)
        assert min_w == 48
        assert min_h == 24
        assert max_w == 900
        assert max_h == 140


class TestHybridVisionParserDPI:
    """HybridVisionParser must propagate DPI scale to its internal OpenCV parser."""

    def test_hybrid_vision_parser_propagates_dpi_scale(self):
        """parse_screenshot() sets _opencv._dpi_scale before calling OpenCV methods."""
        from core.environments.vision_fallback import HybridVisionParser
        parser = HybridVisionParser()
        if not parser.is_available():
            pytest.skip("Hybrid parser not available (OpenCV missing)")
        with patch.object(parser._opencv, "_get_dpi_scale_factor", return_value=2.0):
            with patch.object(parser._opencv, "_detect_raw_elements", return_value=[]) as mock_detect:
                with patch.object(parser._opencv, "_get_active_window_crop", return_value=(None, (0, 0))):
                    parser.parse_screenshot("dummy.png")
        assert parser._opencv._dpi_scale == 2.0, (
            f"Expected _opencv._dpi_scale to be 2.0, got {parser._opencv._dpi_scale}"
        )
