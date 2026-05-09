# Desktop Automation gRPC Server (Standalone Test Version)
# This module provides a standalone gRPC server for testing the Rust desktop automation bridge

import asyncio
import grpc
import grpc.aio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import base64
import os
import sys

# Add the parent directory to sys.path to import protobuf modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import generated gRPC code
try:
    import desktop_pb2
    import desktop_pb2_grpc
    print("✓ Successfully imported protobuf modules")
except ImportError as e:
    print(f"✗ Failed to import protobuf: {e}")
    print("Note: This is a standalone test server. protobuf modules need to be generated from desktop.proto")
    print("Skipping protobuf-dependent code - server will run in stub mode")
    desktop_pb2 = None
    desktop_pb2_grpc = None


@dataclass
class DesktopSession:
    """Simplified desktop session for testing"""
    session_id: str
    created_at: datetime
    last_activity: datetime
    window_count: int = 0
    action_count: int = 0


class DesktopAutomationServicer:
    """Implementation of the DesktopAutomation gRPC service (standalone test version)"""
    
    def __init__(self):
        self.sessions: Dict[str, DesktopSession] = {}
        self.logger = logging.getLogger(__name__)
        
    def _get_or_create_session(self, session_id: str) -> DesktopSession:
        """Get existing session or create new one"""
        if session_id not in self.sessions:
            self.logger.info(f"Creating new desktop session: {session_id}")
            self.sessions[session_id] = DesktopSession(
                session_id=session_id,
                created_at=datetime.now(),
                last_activity=datetime.now(),
                window_count=0,
                action_count=0
            )
        else:
            self.sessions[session_id].last_activity = datetime.now()
        
        return self.sessions[session_id]
    
    async def ScreenCapture(self, request, context):
        """Capture screen region - stub implementation"""
        self.logger.info(f"ScreenCapture called for window: {request.window_id}")
        session = self._get_or_create_session(request.window_id)
        session.action_count += 1
        
        # Return a small test image (1x1 pixel PNG)
        test_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        
        return desktop_pb2.ScreenCaptureResponse(
            image_data=test_png,
            format="png"
        )
    
    async def OcrScreen(self, request, context):
        """Perform OCR - stub implementation"""
        self.logger.info("OcrScreen called")
        
        return desktop_pb2.OcrScreenResponse(
            text="Test OCR Result - This is sample text from the screen",
            confidence=0.95
        )
    
    async def FindWindow(self, request, context):
        """Find window by title - stub implementation"""
        self.logger.info(f"FindWindow called with title: {request.title}")
        
        # Simulate finding a window
        return desktop_pb2.FindWindowResponse(
            window_id="test-window-123",
            title=request.title,
            x=100,
            y=100,
            width=800,
            height=600,
            found=True
        )
    
    async def Click(self, request, context):
        """Click at coordinates - stub implementation"""
        self.logger.info(f"Click called at ({request.x}, {request.y}) on window {request.window_id}")
        session = self._get_or_create_session(request.window_id)
        session.action_count += 1
        
        return desktop_pb2.ClickResponse(
            success=True
        )
    
    async def Type(self, request, context):
        """Type text - stub implementation"""
        self.logger.info(f"Type called with text: '{request.text}' on window {request.window_id}")
        session = self._get_or_create_session(request.window_id)
        session.action_count += 1
        
        return desktop_pb2.TypeResponse(
            success=True
        )
    
    async def Observe(self, request, context):
        """Observe desktop state - stub implementation"""
        self.logger.info(f"Observe called for session: {request.session_id}")
        session = self._get_or_create_session(request.session_id)
        session.window_count = 5  # Simulated window count
        
        # Create window info list
        windows = [
            desktop_pb2.WindowInfo(
                id="window-1",
                title="Test Window 1",
                x=0, y=0, width=1920, height=1080
            ),
            desktop_pb2.WindowInfo(
                id="window-2",
                title="Notepad",
                x=100, y=100, width=800, height=600
            ),
            desktop_pb2.WindowInfo(
                id="window-3",
                title="Calculator",
                x=200, y=200, width=400, height=600
            )
        ]
        
        return desktop_pb2.ObserveResponse(
            observation_id="obs-001",
            timestamp=datetime.now().isoformat(),
            window_count=3,
            windows=windows,
            text_content="Test window content from OCR",
            screenshot_available=True
        )
    
    async def Decide(self, request, context):
        """Decision step - stub implementation"""
        self.logger.info(f"Decide called for observation: {request.observation_id}")
        
        action = desktop_pb2.Action(
            action_type="click",
            target="window",
            x=500,
            y=300,
            confidence=0.85
        )
        
        return desktop_pb2.DecideResponse(
            observation_id=request.observation_id,
            action=action
        )
    
    async def Act(self, request, context):
        """Action step - stub implementation"""
        self.logger.info(f"Act called for session: {request.session_id}, action: {request.action.action_type}")
        session = self._get_or_create_session(request.session_id)
        session.action_count += 1
        
        return desktop_pb2.ActResponse(
            success=True,
            action_id=request.action.action_id,
            screenshot=b""  # Empty screenshot for stub
        )
    
    async def Verify(self, request, context):
        """Verification step - stub implementation"""
        self.logger.info(f"Verify called for session: {request.session_id}")
        
        return desktop_pb2.VerifyResponse(
            verified=True,
            confidence=0.9,
            notes="Verification passed (stub)"
        )
    
    async def Recover(self, request, context):
        """Recovery step - stub implementation"""
        self.logger.info(f"Recover called for session: {request.session_id}, failure: {request.failure_type}")
        
        return desktop_pb2.RecoveryResponse(
            success=True,
            recovery_action="retry",
            notes="Recovery attempted (stub)"
        )
    
    async def CloseSession(self, request, context):
        """Close desktop session - stub implementation"""
        self.logger.info(f"CloseSession called for: {request.session_id}")
        
        if request.session_id in self.sessions:
            del self.sessions[request.session_id]
            self.logger.info(f"Session {request.session_id} closed")
        
        return desktop_pb2.CloseSessionResponse(success=True)


async def serve_async(port: int = 50051):
    """Start the async gRPC server"""
    server = grpc.aio.server()
    
    if desktop_pb2 and desktop_pb2_grpc:
        desktop_pb2_grpc.add_DesktopAutomationServicer_to_server(
            DesktopAutomationServicer(), server
        )
        logging.info(f"✓ gRPC service registered")
    else:
        logging.error("✗ Cannot start server - protobuf modules not available")
        return
    
    server.add_insecure_port(f'[::]:{port}')
    await server.start()
    logging.info(f"✓ Desktop Automation gRPC server started on port {port}")
    logging.info(f"✓ Server ready to accept connections")
    
    # Print server info
    print("\n" + "="*60)
    print("DESKTOP AUTOMATION gRPC SERVER - TEST MODE")
    print("="*60)
    print(f"Server Address: 0.0.0.0:{port}")
    print(f"Status: RUNNING")
    print(f"\nAvailable RPCs:")
    print("  - ScreenCapture")
    print("  - OcrScreen")
    print("  - FindWindow")
    print("  - Click")
    print("  - Type")
    print("  - Observe")
    print("  - Decide")
    print("  - Act")
    print("  - Verify")
    print("  - Recover")
    print("  - CloseSession")
    print("\nPress Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logging.info("Server shutting down...")
        await server.stop(5)


def serve(port: int = 50051):
    """Start the gRPC server (sync wrapper for async)"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(serve_async(port))


if __name__ == '__main__':
    port = int(os.environ.get("GRPC_PORT", "50051"))
    serve(port)
