"""Hardened lightweight vision fallback for desktop UI element detection.

When the accessibility tree fails or returns sparse results, this module
parses a screenshot using OpenCV heuristics to detect actionable UI regions.

Key hardening over the previous version:
- Crops to the active/focused window only (ignores desktop/taskbar/other apps)
- Excludes Windows taskbar and system UI regions explicitly
- Filters out standalone text spam; keeps only text near actionable controls
- Higher confidence thresholds with stricter size filters
- Ranks elements by actionability + confidence + centrality
- Caps output to 20 elements max
- Coordinates are always returned in original screen space

Architecture:
- VisionFallbackParser is the base interface.
- OpenCVFallbackParser implements contour + MSER based detection.
- OmniParserAdapter (future) can replace OpenCVFallbackParser for higher accuracy.

Output format matches the accessibility tree so existing tools (click_element,
type_element, etc.) work transparently.
"""

import json
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional OpenCV (graceful degradation)
try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore

# Optional win32gui for window detection
try:
    import win32gui
except Exception:
    win32gui = None  # type: ignore


class DetectedElement:
    """A UI element discovered by vision parsing."""

    def __init__(
        self,
        element_id: int,
        bbox: Tuple[int, int, int, int],  # x, y, w, h  (screen-space)
        element_type: str = "custom",
        label: str = "",
        confidence: float = 0.0,
    ):
        self.id = element_id
        self.bbox = bbox
        self.type = element_type
        self.label = label
        self.confidence = confidence

    def to_tree_node(self) -> Dict[str, Any]:
        x, y, w, h = self.bbox
        center = (x + w // 2, y + h // 2) if w > 0 and h > 0 else None
        return {
            "id": self.id,
            "type": self.type,
            "name": self.label or f"{self.type} {self.id}",
            "value": None,
            "auto_id": None,
            "class_name": None,
            "is_enabled": True,
            "is_focusable": self.type in {"button", "edit", "checkbox", "combobox", "hyperlink", "listitem", "menuitem", "radiobutton", "slider", "spinner", "splitbutton", "tabitem", "treeitem"},
            "center": center,
            "vision": True,
            "confidence": round(self.confidence, 2),
        }

    def to_element_map_entry(self) -> Dict[str, Any]:
        x, y, w, h = self.bbox
        center = (x + w // 2, y + h // 2) if w > 0 and h > 0 else None
        return {
            "element": None,  # No COM element; we use coordinates
            "center": center,
            "name": self.label or f"{self.type} {self.id}",
            "type": self.type,
            "bbox": self.bbox,
        }


class VisionFallbackParser:
    """Base class for vision-based UI parsers."""

    def parse_screenshot(self, screenshot_path: str) -> List[DetectedElement]:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


class OpenCVFallbackParser(VisionFallbackParser):
    """Fast, lightweight UI element detection using OpenCV heuristics.

    No ML models required. Works entirely with classical computer vision:
    - MSER for text region detection
    - Contour analysis for button / input / icon detection
    - Aspect-ratio and size heuristics for classification

    Hardened rules:
    - Only scans the active window region (cropped from full screenshot)
    - Excludes taskbar / system tray
    - Filters standalone text; keeps text near actionable controls
    - Higher confidence thresholds
    - Caps output to 20 best elements
    """

    # Hard constants -------------------------------------------------------
    MAX_ELEMENTS = 20
    TASKBAR_HEIGHT_ESTIMATE = 64  # px; used only when window rect unavailable
    TEXT_PROXIMITY_PX = 40  # text must be within this distance of a control
    MIN_CONFIDENCE = {
        "button": 0.55,
        "edit": 0.55,
        "checkbox": 0.50,
        "image": 0.50,
        "text": 0.50,
        "slider": 0.50,
        "custom": 0.50,
    }

    def is_available(self) -> bool:
        return cv2 is not None and np is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_screenshot(self, screenshot_path: str) -> List[DetectedElement]:
        if not self.is_available():
            logger.warning("OpenCV fallback not available: cv2 or numpy missing")
            return []

        img = cv2.imread(screenshot_path)
        if img is None:
            logger.warning(f"OpenCV fallback: could not read screenshot {screenshot_path}")
            return []

        full_h, full_w = img.shape[:2]

        # 1. Determine region of interest: active window
        crop_rect, window_offset = self._get_active_window_crop(full_w, full_h)
        if crop_rect:
            cx, cy, cw, ch = crop_rect
            # Clamp
            cx = max(0, min(cx, full_w - 1))
            cy = max(0, min(cy, full_h - 1))
            cw = max(1, min(cw, full_w - cx))
            ch = max(1, min(ch, full_h - cy))
            roi_img = img[cy : cy + ch, cx : cx + cw]
            logger.info(
                f"OpenCV fallback: cropped to active window rect ({cx},{cy},{cw},{ch})"
            )
        else:
            # No window detected — exclude taskbar at bottom
            roi_img = img[: full_h - self.TASKBAR_HEIGHT_ESTIMATE, :]
            window_offset = (0, 0)
            logger.info(
                f"OpenCV fallback: no active window found; excluding bottom {self.TASKBAR_HEIGHT_ESTIMATE}px taskbar"
            )

        if roi_img.size == 0:
            logger.warning("OpenCV fallback: ROI is empty after cropping")
            return []

        # 2. Detect raw elements inside ROI
        raw_elements = self._detect_raw_elements(roi_img)
        if not raw_elements:
            return []

        # 3. Offset coordinates back to full-screen space
        for elem in raw_elements:
            x, y, w, h = elem.bbox
            elem.bbox = (x + window_offset[0], y + window_offset[1], w, h)

        # 4. Filter text spam: keep text only if near an actionable control
        filtered = self._filter_text_spam(raw_elements)

        # 5. Apply confidence floor
        filtered = [
            e for e in filtered
            if e.confidence >= self.MIN_CONFIDENCE.get(e.type, 0.5)
        ]

        # 6. Rank and cap
        ranked = self._rank_elements(filtered, full_w, full_h)
        final = ranked[: self.MAX_ELEMENTS]

        # 7. Re-assign sequential IDs
        for new_id, elem in enumerate(final, start=1):
            elem.id = new_id

        logger.info(
            f"OpenCV fallback: returned {len(final)} elements after hardening "
            f"(from {len(raw_elements)} raw detections)"
        )
        return final

    # ------------------------------------------------------------------
    # Window / ROI helpers
    # ------------------------------------------------------------------

    def _get_active_window_crop(
        self, full_w: int, full_h: int
    ) -> Tuple[Optional[Tuple[int, int, int, int]], Tuple[int, int]]:
        """Return (crop_rect, window_offset) for the foreground window.

        On Windows uses win32gui.GetForegroundWindow + GetWindowRect.
        Falls back to uiautomation if win32gui unavailable.
        Returns (None, (0,0)) if no foreground window can be determined.
        """
        if sys.platform != "win32":
            return None, (0, 0)

        # Try win32gui first
        if win32gui is not None:
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                    # Sanity: window must be on-screen and reasonably sized
                    if right > left and bottom > top:
                        if left < full_w and top < full_h:
                            cx = max(0, left)
                            cy = max(0, top)
                            cw = min(right - left, full_w - cx)
                            ch = min(bottom - top, full_h - cy)
                            if cw > 50 and ch > 50:
                                return (cx, cy, cw, ch), (cx, cy)
            except Exception as e:
                logger.debug(f"win32gui foreground window detection failed: {e}")

        # Fallback to uiautomation
        try:
            import uiautomation as auto
            fw = auto.GetForegroundControl()
            if fw and hasattr(fw, "BoundingRectangle"):
                rect = fw.BoundingRectangle
                if rect and rect.right > rect.left and rect.bottom > rect.top:
                    cx = max(0, rect.left)
                    cy = max(0, rect.top)
                    cw = min(rect.right - rect.left, full_w - cx)
                    ch = min(rect.bottom - rect.top, full_h - cy)
                    if cw > 50 and ch > 50:
                        return (cx, cy, cw, ch), (cx, cy)
        except Exception as e:
            logger.debug(f"uiautomation foreground window detection failed: {e}")

        return None, (0, 0)

    # ------------------------------------------------------------------
    # Raw detection (cropped image space)
    # ------------------------------------------------------------------

    def _detect_raw_elements(self, img: Any) -> List[DetectedElement]:
        h, w = img.shape[:2]
        elements: List[DetectedElement] = []
        element_id = 1
        detected_boxes: List[Tuple[int, int, int, int]] = []

        def add_element(bbox, elem_type, confidence=0.5, label=""):
            nonlocal element_id
            x, y, bw, bh = bbox
            x = max(0, min(x, w - 1))
            y = max(0, min(y, h - 1))
            bw = max(1, min(bw, w - x))
            bh = max(1, min(bh, h - y))
            if bw < 3 or bh < 3:
                return
            for existing in detected_boxes:
                if self._iou((x, y, bw, bh), existing) > 0.55:
                    return
            detected_boxes.append((x, y, bw, bh))
            elements.append(
                DetectedElement(
                    element_id=element_id,
                    bbox=(x, y, bw, bh),
                    element_type=elem_type,
                    label=label or f"{elem_type} {element_id}",
                    confidence=confidence,
                )
            )
            element_id += 1

        # 1. UI primitives (buttons, edits, checkboxes)
        ui_boxes = self._detect_ui_primitives(img)
        for bbox, elem_type, confidence in ui_boxes:
            add_element(bbox, elem_type, confidence=confidence)

        # 2. Flat buttons (edge-based, for modern UIs)
        edge_boxes = self._detect_flat_buttons(img)
        for bbox in edge_boxes:
            add_element(bbox, "button", confidence=0.55, label="Button")

        # 3. Text regions (MSER)
        text_boxes = self._detect_text_regions(img)
        for bbox in text_boxes:
            add_element(bbox, "text", confidence=0.50, label="Text")

        return elements

    # ------------------------------------------------------------------
    # Post-processing filters
    # ------------------------------------------------------------------

    def _filter_text_spam(self, elements: List[DetectedElement]) -> List[DetectedElement]:
        """Keep text regions only if they overlap or are near actionable controls."""
        controls = [e for e in elements if e.type in {"button", "edit", "checkbox", "image", "slider"}]
        if not controls:
            # No controls found — keep nothing (too risky to guess)
            return [e for e in elements if e.type != "text"]

        kept: List[DetectedElement] = []
        for elem in elements:
            if elem.type != "text":
                kept.append(elem)
                continue
            # Keep text if it overlaps or is near a control
            if self._is_near_any_control(elem, controls, threshold_px=self.TEXT_PROXIMITY_PX):
                kept.append(elem)
        return kept

    @staticmethod
    def _is_near_any_control(
        text_elem: DetectedElement,
        controls: List[DetectedElement],
        threshold_px: int = 40,
    ) -> bool:
        tx, ty, tw, th = text_elem.bbox
        tcx, tcy = tx + tw // 2, ty + th // 2
        for ctrl in controls:
            cx, cy, cw, ch = ctrl.bbox
            # Distance from text center to control center
            ccx, ccy = cx + cw // 2, cy + ch // 2
            if abs(tcx - ccx) <= (tw // 2 + cw // 2 + threshold_px) and \
               abs(tcy - ccy) <= (th // 2 + ch // 2 + threshold_px):
                return True
        return False

    def _rank_elements(
        self,
        elements: List[DetectedElement],
        full_w: int,
        full_h: int,
    ) -> List[DetectedElement]:
        """Rank by: actionability weight * confidence * center proximity."""
        cx, cy = full_w / 2, full_h / 2
        type_weights = {
            "button": 1.0,
            "edit": 1.0,
            "checkbox": 0.92,
            "image": 0.65,
            "slider": 0.60,
            "text": 0.45,
            "custom": 0.40,
        }

        scored = []
        for elem in elements:
            ex, ey, ew, eh = elem.bbox
            ecx, ecy = ex + ew / 2, ey + eh / 2
            # Normalized distance to screen center (0 = center, 1 = corner)
            dist = ((ecx - cx) ** 2 + (ecy - cy) ** 2) ** 0.5
            max_dist = ((cx) ** 2 + (cy) ** 2) ** 0.5
            center_score = max(0.3, 1.0 - (dist / max_dist))  # never drop below 0.3
            weight = type_weights.get(elem.type, 0.4)
            score = weight * elem.confidence * center_score
            scored.append((score, elem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored]

    # ------------------------------------------------------------------
    # Internal detectors
    # ------------------------------------------------------------------

    def _detect_text_regions(self, img: Any) -> List[Tuple[int, int, int, int]]:
        """Use MSER to find text-like regions."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mser = cv2.MSER_create()
        mser.setMinArea(100)
        mser.setMaxArea(6000)
        regions, _ = mser.detectRegions(gray)
        boxes = []
        for region in regions:
            x, y, bw, bh = cv2.boundingRect(region.reshape(-1, 1, 2))
            # Tight filters
            if bw < 24 or bh < 12 or bw > 450 or bh > 70:
                continue
            aspect = bw / max(bh, 1)
            if aspect < 1.5 or aspect > 22:
                continue
            boxes.append((x, y, bw, bh))
        return self._merge_boxes(boxes, iou_threshold=0.3)

    def _detect_ui_primitives(self, img: Any) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
        """Detect buttons, edits, checkboxes via contour analysis.

        Handles both light and dark UIs by auto-detecting background brightness
        and switching threshold direction. Falls back to Canny edges for dark
        flat UIs (Electron, Material Design) where thresholding produces blobs.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = img.shape[:2]
        img_area = w * h
        mean_brightness = gray.mean()
        is_dark = mean_brightness < 100

        results: List[Tuple[Tuple[int, int, int, int], str, float]] = []

        # --- Pass 1: adaptive threshold ----------------------------------
        thresh_type = cv2.THRESH_BINARY if is_dark else cv2.THRESH_BINARY_INV
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, thresh_type, 11, 2
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # If threshold produces a giant blob (>60% of image), it's unusable
        giant_blob = any(
            cv2.boundingRect(cnt)[2] * cv2.boundingRect(cnt)[3] > img_area * 0.5
            for cnt in contours
        )

        if not giant_blob:
            for cnt in contours:
                x, y, bw, bh = cv2.boundingRect(cnt)
                area = bw * bh
                if area < 100 or area > img_area * 0.35:
                    continue
                elem_type, confidence = self._classify_contour(cnt, bw, bh, area)
                if elem_type != "custom":
                    results.append(((x, y, bw, bh), elem_type, confidence))

        # --- Pass 2: Canny edge detector (always run, esp. for dark UIs) --
        canny_results = self._detect_canny_primitives(img)
        results.extend(canny_results)

        return results

    def _classify_contour(
        self, cnt: Any, bw: int, bh: int, area: int
    ) -> Tuple[str, float]:
        """Classify a single contour into a UI element type."""
        aspect = bw / max(bh, 1)
        perimeter = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * perimeter, True)
        num_corners = len(approx)

        # Checkbox / radio: small square-ish
        if 0.7 <= aspect <= 1.4 and 18 <= bw <= 52 and 18 <= bh <= 52:
            if num_corners >= 4:
                return "checkbox", 0.60

        # Button: medium rectangle, roughly 4-10 corners (rounded rects)
        if 0.3 <= aspect <= 4.0 and 30 <= bw <= 340 and 22 <= bh <= 105:
            if 4 <= num_corners <= 10:
                fill_ratio = area / (bw * bh)
                conf = 0.65 if fill_ratio > 0.45 else 0.55
                return "button", conf

        # Edit / input: wide, short rectangle
        if aspect >= 2.2 and 18 <= bh <= 70 and bw >= 80:
            return "edit", 0.60

        # Icon / image: small square
        if 0.5 <= aspect <= 2 and 20 <= bw <= 64 and 20 <= bh <= 64 and area < 4096:
            return "image", 0.55

        # Slider / scrollbar: very thin, long
        if (aspect > 10 and bh < 24) or (aspect < 0.12 and bw < 24):
            return "slider", 0.50

        return "custom", 0.4

    def _detect_canny_primitives(
        self, img: Any
    ) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
        """Use Canny edges to find UI elements on dark/flat UIs."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 130)
        # Dilation merges thin edges on dark flat UIs into giant blobs;
        # skip it for dark backgrounds where edges are already faint.
        if gray.mean() >= 100:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results: List[Tuple[Tuple[int, int, int, int], str, float]] = []
        h, w = img.shape[:2]
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if area < 150 or area > (w * h * 0.30):
                continue
            aspect = bw / max(bh, 1)

            # Canny produces edge outlines; the bounding rect is slightly larger
            # than the actual element, so be more permissive with sizes.
            elem_type = "custom"
            confidence = 0.4

            if 0.3 <= aspect <= 4.0 and 28 <= bw <= 360 and 20 <= bh <= 110:
                elem_type = "button"
                confidence = 0.55
            elif aspect >= 2.2 and 16 <= bh <= 75 and bw >= 70:
                elem_type = "edit"
                confidence = 0.55
            elif 0.7 <= aspect <= 1.4 and 16 <= bw <= 55 and 16 <= bh <= 55:
                elem_type = "checkbox"
                confidence = 0.50
            elif 0.5 <= aspect <= 2 and 18 <= bw <= 70 and 18 <= bh <= 70 and area < 4900:
                elem_type = "image"
                confidence = 0.50
            elif (aspect > 10 and bh < 24) or (aspect < 0.12 and bw < 24):
                elem_type = "slider"
                confidence = 0.45

            if elem_type != "custom":
                results.append(((x, y, bw, bh), elem_type, confidence))

        return results

    def _detect_flat_buttons(self, img: Any) -> List[Tuple[int, int, int, int]]:
        """Detect flat buttons using Canny edges."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 40, 130)
        if gray.mean() >= 100:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        h, w = img.shape[:2]
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if area < 400 or area > (w * h * 0.25):
                continue
            aspect = bw / max(bh, 1)
            if 0.3 <= aspect <= 4.5 and 30 <= bw <= 320 and 22 <= bh <= 110:
                boxes.append((x, y, bw, bh))
        return self._merge_boxes(boxes, iou_threshold=0.5)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        inter_x1 = max(ax, bx)
        inter_y1 = max(ay, by)
        inter_x2 = min(ax + aw, bx + bw)
        inter_y2 = min(ay + ah, by + bh)
        inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
        union_area = aw * ah + bw * bh - inter_area
        return inter_area / union_area if union_area > 0 else 0.0

    @staticmethod
    def _merge_boxes(
        boxes: List[Tuple[int, int, int, int]],
        iou_threshold: float = 0.3,
    ) -> List[Tuple[int, int, int, int]]:
        if not boxes:
            return []
        boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
        merged: List[Tuple[int, int, int, int]] = []
        for box in boxes:
            keep = True
            for m in merged:
                if OpenCVFallbackParser._iou(box, m) > iou_threshold:
                    keep = False
                    break
            if keep:
                merged.append(box)
        return merged


class HybridVisionParser(VisionFallbackParser):
    """Three-tier vision fallback: OpenCV → OmniParser escalation.

    Flow:
    1. Crop screenshot to active window (excludes taskbar/desktop)
    2. Run OpenCV heuristics (fast, ~50-200ms)
    3. If OpenCV result is strong (≥3 actionable elements): use it
    4. If OpenCV is weak (0-2 actionable): escalate to OmniParser v2
       (slow, ~2-5s on CPU, but handles Electron/dark UIs)
    5. Apply shared filtering, ranking, capping, and coordinate offset

    Observability:
    - Logs ``vision_mode`` (opencv / omniparser)
    - Logs ``fallback_reason`` (sparse_tree / opencv_failure / opencv_weak)
    """

    # Escalation threshold: if OpenCV yields fewer than this actionable
    # elements, we try OmniParser as a second fallback.
    OPENCV_ACTIONABLE_THRESHOLD = 3

    def __init__(self):
        self._opencv = OpenCVFallbackParser()
        self._omni = None  # Lazy import to avoid startup overhead

    def is_available(self) -> bool:
        return self._opencv.is_available()

    def _get_omni(self):
        if self._omni is None:
            try:
                from .omniparser_client import get_omni_parser, OmniParserClient
                self._omni = get_omni_parser()
            except Exception as e:
                logger.debug(f"HybridVisionParser: OmniParser not available: {e}")
                self._omni = False  # sentinel: tried and failed
        return self._omni if isinstance(self._omni, OmniParserClient) else None

    def parse_screenshot(self, screenshot_path: str) -> List[DetectedElement]:
        if not self.is_available():
            logger.warning("HybridVisionParser: OpenCV not available")
            return []

        img = cv2.imread(screenshot_path)
        if img is None:
            logger.warning(f"HybridVisionParser: could not read screenshot {screenshot_path}")
            return []

        full_h, full_w = img.shape[:2]

        # 1. Crop to active window -------------------------------------
        crop_rect, window_offset = self._opencv._get_active_window_crop(full_w, full_h)
        if crop_rect:
            cx, cy, cw, ch = crop_rect
            cx = max(0, min(cx, full_w - 1))
            cy = max(0, min(cy, full_h - 1))
            cw = max(1, min(cw, full_w - cx))
            ch = max(1, min(ch, full_h - cy))
            roi_img = img[cy : cy + ch, cx : cx + cw]
            logger.info(
                f"HybridVisionParser: cropped to active window ({cx},{cy},{cw},{ch})"
            )
        else:
            roi_img = img[: full_h - self._opencv.TASKBAR_HEIGHT_ESTIMATE, :]
            window_offset = (0, 0)
            logger.info(
                f"HybridVisionParser: no window found; excluding taskbar"
            )

        if roi_img.size == 0:
            logger.warning("HybridVisionParser: ROI is empty")
            return []

        # 2. OpenCV pass (fast) ----------------------------------------
        opencv_raw = self._opencv._detect_raw_elements(roi_img)
        # Offset to screen space
        for elem in opencv_raw:
            x, y, w, h = elem.bbox
            elem.bbox = (x + window_offset[0], y + window_offset[1], w, h)

        opencv_filtered = self._opencv._filter_text_spam(opencv_raw)
        opencv_filtered = [
            e for e in opencv_filtered
            if e.confidence >= self._opencv.MIN_CONFIDENCE.get(e.type, 0.5)
        ]
        opencv_actionable = sum(
            1 for e in opencv_filtered
            if e.type in {"button", "edit", "checkbox", "combobox", "hyperlink",
                          "listitem", "menuitem", "radiobutton", "slider",
                          "spinner", "splitbutton", "tabitem", "treeitem"}
        )

        logger.info(
            f"HybridVisionParser: OpenCV raw={len(opencv_raw)} "
            f"filtered={len(opencv_filtered)} actionable={opencv_actionable}"
        )

        # 3. Decide whether to escalate --------------------------------
        use_opencv = (
            len(opencv_filtered) > 0
            and opencv_actionable >= self.OPENCV_ACTIONABLE_THRESHOLD
        )

        if use_opencv:
            final = self._finalize(opencv_filtered, full_w, full_h)
            logger.info(
                f"vision_mode=opencv fallback_reason=none "
                f"detections={len(final)} actionable={opencv_actionable}"
            )
            return final

        # 4. OmniParser escalation (slow but accurate) -----------------
        fallback_reason = (
            "opencv_failure" if len(opencv_filtered) == 0 else "opencv_weak"
        )
        omni = self._get_omni()
        if omni is not None and omni.is_available():
            logger.info(
                f"HybridVisionParser: escalating to OmniParser "
                f"(reason={fallback_reason}, opencv_actionable={opencv_actionable})"
            )
            try:
                from PIL import Image
                roi_pil = Image.fromarray(cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB))
                omni_results = omni.parse_image(roi_pil)

                if omni_results:
                    # Convert OmniParser output to DetectedElement
                    omni_elements: List[DetectedElement] = []
                    for idx, box_elem in enumerate(omni_results, start=1):
                        bbox = box_elem["bbox"]  # [x1, y1, x2, y2] in pixel space
                        x1, y1, x2, y2 = map(int, bbox)
                        w = x2 - x1
                        h = y2 - y1
                        elem_type = self._map_omni_type(box_elem["type"])
                        label = box_elem.get("content") or f"{elem_type} {idx}"
                        confidence = 0.75 if box_elem.get("interactivity") else 0.60
                        omni_elements.append(
                            DetectedElement(
                                element_id=idx,
                                bbox=(x1 + window_offset[0], y1 + window_offset[1], w, h),
                                element_type=elem_type,
                                label=label,
                                confidence=confidence,
                            )
                        )

                    # Deduplicate against OpenCV results (keep OmniParser)
                    merged = self._merge_opencv_omni(opencv_filtered, omni_elements)
                    final = self._finalize(merged, full_w, full_h)
                    logger.info(
                        f"vision_mode=omniparser fallback_reason={fallback_reason} "
                        f"detections={len(final)}"
                    )
                    return final
                else:
                    logger.warning(
                        f"vision_mode=omniparser fallback_reason={fallback_reason} "
                        f"detections=0 (OmniParser returned no elements)"
                    )
            except Exception as e:
                logger.error(f"HybridVisionParser: OmniParser failed: {e}")
        else:
            logger.warning(
                f"HybridVisionParser: OmniParser not available, staying with weak OpenCV"
            )

        # 5. Fallback to OpenCV even if weak ---------------------------
        final = self._finalize(opencv_filtered, full_w, full_h)
        logger.info(
            f"vision_mode=opencv fallback_reason={fallback_reason} "
            f"detections={len(final)} (weak result, no escalation possible)"
        )
        return final

    @staticmethod
    def _map_omni_type(omni_type: str) -> str:
        """Map OmniParser type strings to our element types."""
        mapping = {
            "text": "text",
            "icon": "button",  # icons are usually clickable buttons
        }
        return mapping.get(omni_type, "custom")

    @staticmethod
    def _merge_opencv_omni(
        opencv: List[DetectedElement],
        omni: List[DetectedElement],
    ) -> List[DetectedElement]:
        """Merge OpenCV + OmniParser results, preferring OmniParser on overlap."""
        if not opencv:
            return omni
        if not omni:
            return opencv

        kept_omni = list(omni)
        for oc_elem in opencv:
            overlaps = False
            ox, oy, ow, oh = oc_elem.bbox
            for om_elem in omni:
                mx, my, mw, mh = om_elem.bbox
                inter_w = max(0, min(ox + ow, mx + mw) - max(ox, mx))
                inter_h = max(0, min(oy + oh, my + mh) - max(oy, my))
                inter_area = inter_w * inter_h
                oc_area = ow * oh
                if oc_area > 0 and inter_area / oc_area > 0.5:
                    overlaps = True
                    break
            if not overlaps:
                kept_omni.append(oc_elem)
        return kept_omni

    def _finalize(
        self,
        elements: List[DetectedElement],
        full_w: int,
        full_h: int,
    ) -> List[DetectedElement]:
        """Apply ranking, capping, and ID reassignment."""
        ranked = self._opencv._rank_elements(elements, full_w, full_h)
        capped = ranked[: self._opencv.MAX_ELEMENTS]
        for new_id, elem in enumerate(capped, start=1):
            elem.id = new_id
        return capped


def get_vision_parser() -> VisionFallbackParser:
    """Return the best available vision parser (Hybrid with escalation)."""
    parser = HybridVisionParser()
    if parser.is_available():
        logger.info("Vision fallback: using HybridVisionParser (OpenCV → OmniParser)")
        return parser
    logger.warning("Vision fallback: no parser available")
    return OpenCVFallbackParser()
