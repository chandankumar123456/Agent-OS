"""Desktop Automation REST API

Provides HTTP endpoints for desktop automation operations.
These endpoints delegate to the existing desktop automation infrastructure
(DesktopSession, WindowRegistry, etc.) for real operations.

In desktop/gRPC mode, these are accessed via Supervisor proxy.
"""

import io
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image

from ...logs.logger import logger

router = APIRouter(prefix="/desktop", tags=["desktop"])

# ─── Models ───────────────────────────────────────────────────

class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"
    clicks: int = 1

class TypeRequest(BaseModel):
    text: str
    interval_ms: int = 50

class FocusRequest(BaseModel):
    title: str

class FindRequest(BaseModel):
    text: str

# ─── Desktop Engine ───────────────────────────────────────────

class DesktopEngine:
    """Provides desktop automation operations using pyautogui/uiautomation/mss."""

    def __init__(self):
        self._pyautogui = None
        self._uia = None
        self._mss = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            self._pyautogui = pyautogui
        except ImportError:
            logger.warning("pyautogui not available, desktop actions will fail")

        try:
            import uiautomation as uia
            self._uia = uia
        except ImportError:
            logger.warning("uiautomation not available, window ops limited")

        try:
            import mss
            self._mss = mss.mss()
        except ImportError:
            logger.warning("mss not available, screenshots limited")

        self._initialized = True

    def screenshot(self, window_title: Optional[str] = None) -> bytes:
        """Take a screenshot, optionally of a specific window by title."""
        self._ensure_initialized()

        if window_title:
            # Try to focus and capture specific window
            try:
                self.focus_window(window_title)
            except HTTPException:
                logger.warning(f"Window '{window_title}' not found, capturing full screen")

        if self._mss:
            monitor = self._mss.monitors[1]  # Primary monitor
            sct_img = self._mss.grab(monitor)
            output = io.BytesIO()
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.save(output, format="PNG")
            return output.getvalue()
        elif self._pyautogui:
            img = self._pyautogui.screenshot()
            output = io.BytesIO()
            img.save(output, format="PNG")
            return output.getvalue()
        else:
            raise HTTPException(status_code=501, detail="No screenshot library available (install mss or pyautogui)")

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1):
        """Click at screen coordinates."""
        self._ensure_initialized()
        if not self._pyautogui:
            raise HTTPException(status_code=501, detail="pyautogui not available")

        btn = button.lower()
        self._pyautogui.click(x, y, clicks=clicks, button=btn)
        logger.info(f"Desktop: clicked at ({x}, {y}) with {btn}")

    def type_text(self, text: str, interval_ms: int = 50):
        """Type text at current cursor position."""
        self._ensure_initialized()
        if not self._pyautogui:
            raise HTTPException(status_code=501, detail="pyautogui not available")

        self._pyautogui.typewrite(text, interval=interval_ms / 1000.0)
        logger.info(f"Desktop: typed {len(text)} characters")

    def focus_window(self, title: str) -> bool:
        """Focus a window by title."""
        self._ensure_initialized()

        if self._uia:
            window = self._uia.WindowControl(searchDepth=1, Name=title)
            if window.Exists(maxSearchSeconds=2):
                window.SetFocus()
                logger.info(f"Desktop: focused window '{title}'")
                return True

        # Fallback: try pygetwindow
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title)
            if windows:
                windows[0].activate()
                logger.info(f"Desktop: focused window '{title}' via pygetwindow")
                return True
        except ImportError:
            pass

        raise HTTPException(status_code=404, detail=f"Window '{title}' not found")

    def list_windows(self, filter_text: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all visible windows."""
        windows = []

        try:
            import pygetwindow as gw
            all_windows = gw.getAllWindows()
            for w in all_windows:
                if not w.title:
                    continue
                if filter_text and filter_text.lower() not in w.title.lower():
                    continue
                windows.append({
                    "id": w._hWnd if hasattr(w, '_hWnd') else hash(w.title),
                    "title": w.title,
                    "process_name": "",
                    "pid": 0,
                    "rect": {
                        "x": w.left if hasattr(w, 'left') else 0,
                        "y": w.top if hasattr(w, 'top') else 0,
                        "width": w.width if hasattr(w, 'width') else 0,
                        "height": w.height if hasattr(w, 'height') else 0,
                    }
                })
        except ImportError:
            logger.warning("pygetwindow not available, listing windows via uiautomation")
            if self._uia:
                for w in self._uia.GetRootControl().GetChildren():
                    if w.Name:
                        windows.append({
                            "id": hash(w.Name),
                            "title": w.Name,
                            "process_name": w.ClassName if hasattr(w, 'ClassName') else "",
                            "pid": 0,
                            "rect": {
                                "x": w.BoundingRectangle.x if hasattr(w, 'BoundingRectangle') else 0,
                                "y": w.BoundingRectangle.y if hasattr(w, 'BoundingRectangle') else 0,
                                "width": w.BoundingRectangle.width() if hasattr(w, 'BoundingRectangle') else 0,
                                "height": w.BoundingRectangle.height() if hasattr(w, 'BoundingRectangle') else 0,
                            }
                        })

        return windows

    def find_element(self, text: str) -> Optional[Dict[str, Any]]:
        """Find an element on screen by text (OCR-based)."""
        self._ensure_initialized()

        # Take screenshot first
        screenshot_bytes = self.screenshot()

        # Try OCR
        try:
            import pytesseract
            img = Image.open(io.BytesIO(screenshot_bytes))
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            for i in range(len(data["text"])):
                if text.lower() in data["text"][i].lower():
                    confidence = int(data["conf"][i]) / 100.0 if data["conf"][i] != "-1" else 0.5
                    return {
                        "text": data["text"][i],
                        "rect": {
                            "x": data["left"][i],
                            "y": data["top"][i],
                            "width": data["width"][i],
                            "height": data["height"][i],
                        },
                        "confidence": confidence,
                    }
        except ImportError:
            logger.warning("pytesseract not available, cannot find element by text")
            raise HTTPException(status_code=501, detail="pytesseract not available for text search")

        return None


# Singleton desktop engine
_desktop_engine = DesktopEngine()


# ─── Routes ───────────────────────────────────────────────────

@router.get("/screenshot")
async def take_screenshot(window: Optional[str] = Query(None)):
    """Take a screenshot. Returns PNG image bytes."""
    try:
        image_data = _desktop_engine.screenshot(window)
        return Response(content=image_data, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screenshot failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/click")
async def click(request: ClickRequest):
    """Click at screen coordinates."""
    try:
        _desktop_engine.click(request.x, request.y, request.button, request.clicks)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Click failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/type")
async def type_text(request: TypeRequest):
    """Type text at current cursor position."""
    try:
        _desktop_engine.type_text(request.text, request.interval_ms)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Type text failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/focus")
async def focus_window(request: FocusRequest):
    """Focus a window by title."""
    try:
        success = _desktop_engine.focus_window(request.title)
        return {"success": success}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Focus window failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/windows")
async def list_windows(filter: Optional[str] = Query(None)):
    """List all visible windows."""
    try:
        windows = _desktop_engine.list_windows(filter)
        return windows
    except Exception as e:
        logger.error(f"List windows failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/find")
async def find_element(request: FindRequest):
    """Find an element on screen by text using OCR."""
    try:
        result = _desktop_engine.find_element(request.text)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Could not find '{request.text}' on screen")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Find element failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
