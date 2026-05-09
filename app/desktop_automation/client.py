"""Desktop Automation Client Bridge

This module provides a Python client for the Rust desktop automation gRPC server.
It translates Python calls to gRPC requests and handles responses.
"""

import grpc
import base64
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .proto import desktop_automation_pb2, desktop_automation_pb2_grpc


@dataclass
class WindowInfo:
    """Window information structure"""
    title: str
    class_name: str
    hwnd: int
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    rect: Dict[str, int]
    pid: int
    process_name: str


@dataclass
class Screenshot:
    """Screenshot data structure"""
    data: bytes
    width: int
    height: int
    timestamp_ms: int


class DesktopAutomationClient:
    """Python client for Rust desktop automation gRPC server"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        timeout: float = 30.0
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[desktop_automation_pb2_grpc.DesktopAutomationStub] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to the Rust desktop automation server"""
        try:
            self.channel = grpc.insecure_channel(f"{self.host}:{self.port}")
            self.stub = desktop_automation_pb2_grpc.DesktopAutomationStub(self.channel)
            
            # Test connection with initialize
            request = desktop_automation_pb2.InitializeRequest(
                log_level="info",
                enable_ocr=True,
                enable_ui_automation=True
            )
            response = self.stub.Initialize(request, timeout=self.timeout)
            
            if response.success:
                self.connected = True
                return True
            return False
        except grpc.RpcError as e:
            print(f"Failed to connect to desktop automation server: {e}")
            self.connected = False
            return False
    
    def disconnect(self) -> bool:
        """Disconnect from the Rust desktop automation server"""
        try:
            if self.channel:
                self.channel.close()
                self.channel = None
                self.stub = None
                self.connected = False
                return True
            return False
        except Exception as e:
            print(f"Failed to disconnect: {e}")
            return False
    
    # Window management methods
    
    def list_windows(
        self,
        include_minimized: bool = False,
        include_invisible: bool = False
    ) -> List[WindowInfo]:
        """List all windows"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.ListWindowsRequest(
            include_minimized=include_minimized,
            include_invisible=include_invisible
        )
        
        try:
            response = self.stub.ListWindows(request, timeout=self.timeout)
            return [
                WindowInfo(
                    title=w.title,
                    class_name=w.class_name,
                    hwnd=w.hwnd,
                    is_visible=w.is_visible,
                    is_minimized=w.is_minimized,
                    is_maximized=w.is_maximized,
                    rect={
                        "left": w.rect.left,
                        "top": w.rect.top,
                        "right": w.rect.right,
                        "bottom": w.rect.bottom,
                        "width": w.rect.width,
                        "height": w.rect.height,
                    },
                    pid=w.pid,
                    process_name=w.process_name
                )
                for w in response.windows
            ]
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to list windows: {e}")
    
    def find_window(self, title_pattern: str, exact_match: bool = False) -> Optional[WindowInfo]:
        """Find window by title pattern"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.FindWindowRequest(
            title_pattern=title_pattern,
            exact_match=exact_match
        )
        
        try:
            response = self.stub.FindWindow(request, timeout=self.timeout)
            if response.found and response.window:
                w = response.window
                return WindowInfo(
                    title=w.title,
                    class_name=w.class_name,
                    hwnd=w.hwnd,
                    is_visible=w.is_visible,
                    is_minimized=w.is_minimized,
                    is_maximized=w.is_maximized,
                    rect={
                        "left": w.rect.left,
                        "top": w.rect.top,
                        "right": w.rect.right,
                        "bottom": w.rect.bottom,
                        "width": w.rect.width,
                        "height": w.rect.height,
                    },
                    pid=w.pid,
                    process_name=w.process_name
                )
            return None
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to find window: {e}")
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """Get currently active window"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.GetActiveWindowRequest()
        
        try:
            response = self.stub.GetActiveWindow(request, timeout=self.timeout)
            if response.success and response.window:
                w = response.window
                return WindowInfo(
                    title=w.title,
                    class_name=w.class_name,
                    hwnd=w.hwnd,
                    is_visible=w.is_visible,
                    is_minimized=w.is_minimized,
                    is_maximized=w.is_maximized,
                    rect={
                        "left": w.rect.left,
                        "top": w.rect.top,
                        "right": w.rect.right,
                        "bottom": w.rect.bottom,
                        "width": w.rect.width,
                        "height": w.rect.height,
                    },
                    pid=w.pid,
                    process_name=w.process_name
                )
            return None
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to get active window: {e}")
    
    # Input simulation methods
    
    def move_mouse(self, x: int, y: int) -> bool:
        """Move mouse to absolute coordinates"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.MoveMouseRequest(x=x, y=y)
        
        try:
            response = self.stub.MoveMouse(request, timeout=self.timeout)
            return response.success
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to move mouse: {e}")
    
    def click_mouse(self, x: int, y: int, button: str = "left") -> bool:
        """Click mouse button at coordinates"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.ClickMouseRequest(x=x, y=y, button=button)
        
        try:
            response = self.stub.ClickMouse(request, timeout=self.timeout)
            return response.success
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to click mouse: {e}")
    
    def double_click(self, x: int, y: int) -> bool:
        """Double click at coordinates"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.DoubleClickRequest(x=x, y=y)
        
        try:
            response = self.stub.DoubleClick(request, timeout=self.timeout)
            return response.success
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to double click: {e}")
    
    def right_click(self, x: int, y: int) -> bool:
        """Right click at coordinates"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.RightClickRequest(x=x, y=y)
        
        try:
            response = self.stub.RightClick(request, timeout=self.timeout)
            return response.success
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to right click: {e}")
    
    def type_text(self, text: str, delay_ms: int = 10) -> bool:
        """Type text using keyboard input"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.TypeTextRequest(text=text, delay_ms=delay_ms)
        
        try:
            response = self.stub.TypeText(request, timeout=self.timeout)
            return response.success
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to type text: {e}")
    
    def press_key(self, key: str) -> bool:
        """Press a single key"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.PressKeyRequest(key=key)
        
        try:
            response = self.stub.PressKey(request, timeout=self.timeout)
            return response.success
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to press key: {e}")
    
    def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse position"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.GetMousePositionRequest()
        
        try:
            response = self.stub.GetMousePosition(request, timeout=self.timeout)
            return (response.x, response.y)
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to get mouse position: {e}")
    
    # Screenshot methods
    
    def screenshot(self, format: str = "png") -> Screenshot:
        """Capture screenshot of entire screen"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.ScreenshotRequest(format=format)
        
        try:
            response = self.stub.Screenshot(request, timeout=self.timeout)
            return Screenshot(
                data=response.image_data,
                width=response.width,
                height=response.height,
                timestamp_ms=response.timestamp_ms
            )
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to take screenshot: {e}")
    
    def screenshot_region(self, x: int, y: int, width: int, height: int, format: str = "png") -> Screenshot:
        """Capture screenshot of a region"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.ScreenshotRegionRequest(
            x=x, y=y, width=width, height=height, format=format
        )
        
        try:
            response = self.stub.ScreenshotRegion(request, timeout=self.timeout)
            return Screenshot(
                data=response.image_data,
                width=response.width,
                height=response.height,
                timestamp_ms=response.timestamp_ms
            )
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to take region screenshot: {e}")
    
    # System info methods
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        if not self.connected:
            raise RuntimeError("Not connected to desktop automation server")
        
        request = desktop_automation_pb2.GetSystemInfoRequest()
        
        try:
            response = self.stub.GetSystemInfo(request, timeout=self.timeout)
            return {
                "screen_width": response.screen_width,
                "screen_height": response.screen_height,
                "dpi_scale": response.dpi_scale,
                "os_version": response.os_version,
                "cpu_count": response.cpu_count,
                "total_memory_mb": response.total_memory_mb,
                "is_admin": response.is_admin,
            }
        except grpc.RpcError as e:
            raise RuntimeError(f"Failed to get system info: {e}")
    
    # Context manager support
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
