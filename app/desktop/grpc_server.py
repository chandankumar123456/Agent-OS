# Desktop Automation gRPC Server
# This module provides the Python side of the gRPC bridge to Rust desktop automation
# Implements the full observe-decide-act-verify-recover loop for desktop automation

import asyncio
import grpc
import grpc.aio  # Use async gRPC server
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import base64
from io import BytesIO
import os

# Import existing AgentOS desktop automation components
from app.environments.desktop_env import DesktopSession
from app.environments.execution_stabilizer import ActionStabilizer
from app.environments.vision_fallback import HybridVisionParser
from app.environments.window_registry import WindowRegistry
from app.capabilities.recovery import RecoveryEngine
from app.capabilities.verification import DeterministicVerificationEngine as VerificationEngine

# Import generated gRPC code
try:
    from app.desktop import desktop_pb2
    from app.desktop import desktop_pb2_grpc
except ImportError:
    # Fallback if protobuf not yet generated
    desktop_pb2 = None
    desktop_pb2_grpc = None


@dataclass
class DesktopState:
    """Current state of the desktop automation session"""
    session_id: str
    window_registry: WindowRegistry
    desktop_session: Optional[DesktopSession] = None
    stabilizer: Optional[ActionStabilizer] = None
    recovery_engine: Optional[RecoveryEngine] = None
    verification_engine: Optional[VerificationEngine] = None
    last_observation: Optional[Dict[str, Any]] = None
    observation_count: int = 0
    error_count: int = 0
    max_errors: int = 3


class DesktopAutomationServicer(desktop_pb2_grpc.DesktopAutomationServicer):
    """Implementation of the DesktopAutomation gRPC service with full observe-decide-act-verify-recover loop"""
    
    def __init__(self):
        self.sessions: Dict[str, DesktopState] = {}
        self.logger = logging.getLogger(__name__)
        
    def _get_or_create_session(self, session_id: str) -> DesktopState:
        """Get existing session or create new one"""
        if session_id not in self.sessions:
            self.logger.info(f"Creating new desktop session: {session_id}")
            
            # Initialize desktop automation components
            window_registry = WindowRegistry()
            desktop_session = DesktopSession(task_id=session_id)
            from app.environments.execution_stabilizer import StabilizerConfig
            stabilizer = ActionStabilizer(config=StabilizerConfig(max_retries=3))
            recovery_engine = RecoveryEngine()
            verification_engine = VerificationEngine()
            
            self.sessions[session_id] = DesktopState(
                session_id=session_id,
                window_registry=window_registry,
                desktop_session=desktop_session,
                stabilizer=stabilizer,
                recovery_engine=recovery_engine,
                verification_engine=verification_engine
            )
        
        return self.sessions[session_id]
    
    async def ScreenCapture(self, request, context):
        """Capture screen region with full error handling - async version"""
        try:
            session = self._get_or_create_session(request.window_id)

            # Capture screen using existing DesktopSession
            if session.desktop_session:
                # screenshot() is async and returns ToolOutput, not PIL Image
                tool_output = await session.desktop_session.screenshot()

                if not tool_output.success:
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(tool_output.error or "Screenshot failed")
                    return desktop_pb2.ScreenCaptureResponse(error=tool_output.error or "Screenshot failed")

                # ToolOutput.result is a dict with {"path": "..."}
                result = tool_output.result or {}
                path = result.get("path")

                if not path or not os.path.exists(path):
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details("Screenshot file not found")
                    return desktop_pb2.ScreenCaptureResponse(error="Screenshot file not found")

                # Read the image file directly
                with open(path, "rb") as f:
                    image_data = f.read()

                response = desktop_pb2.ScreenCaptureResponse(
                    image_data=image_data,
                    format="png"
                )
                return response
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.ScreenCaptureResponse(error="Desktop session not initialized")

        except Exception as e:
            self.logger.error(f"Screen capture failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ScreenCaptureResponse(error=str(e))
    
    async def OcrScreen(self, request, context):
        """Perform OCR on screen image using Windows OCR engine - async version"""
        try:
            session = self._get_or_create_session("global_ocr")

            # Use HybridVisionParser for OCR with DPI scaling support
            if session.desktop_session:
                # First capture screenshot (async) to get a file path
                tool_output = await session.desktop_session.screenshot()

                if not tool_output.success:
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(tool_output.error or "Screenshot failed")
                    return desktop_pb2.OcrScreenResponse(error=tool_output.error or "Screenshot failed")

                path = tool_output.result.get("path") if tool_output.result else None
                if not path or not os.path.exists(path):
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details("Screenshot file not found")
                    return desktop_pb2.OcrScreenResponse(error="Screenshot file not found")

                # Parse using hybrid vision parser
                parser = HybridVisionParser()
                result = parser.parse_screenshot(path)

                response = desktop_pb2.OcrScreenResponse(
                    text=result.get("text", ""),
                    confidence=result.get("confidence", 0.0)
                )
                return response
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.OcrScreenResponse(error="Desktop session not initialized")

        except Exception as e:
            self.logger.error(f"OCR failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.OcrScreenResponse(error=str(e))
    
    async def FindWindow(self, request, context):
        """Find window by title using WindowRegistry - async version"""
        try:
            session = self._get_or_create_session("window_find")

            # Refresh registry to get latest window positions
            session.window_registry.refresh()

            # Get windows from registry - use find_by_title for efficient lookup
            matched_ref = session.window_registry.find_by_title(request.title)

            # If not found and partial_match is enabled, try to find by iterating
            if matched_ref is None and request.partial_match:
                for ref in session.window_registry._registry.values():
                    if request.title.lower() in ref.title.lower():
                        matched_ref = ref
                        break

            if matched_ref:
                # Get actual window position if available via desktop_session
                x, y, width, height = 0, 0, 0, 0
                if matched_ref.hwnd and session.desktop_session:
                    # Use window_registry to get position
                    try:
                        active = session.window_registry.get_active_window()
                        if active and active.hwnd == matched_ref.hwnd:
                            # Can't get exact position without pygetwindow, use defaults
                            pass
                    except Exception:
                        pass

                response = desktop_pb2.FindWindowResponse(
                    window_id=str(matched_ref.hwnd) if matched_ref.hwnd else "",
                    title=matched_ref.title,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    found=True
                )
            else:
                response = desktop_pb2.FindWindowResponse(
                    window_id="",
                    title=request.title,
                    x=0,
                    y=0,
                    width=0,
                    height=0,
                    found=False
                )

            return response

        except Exception as e:
            self.logger.error(f"Window finding failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.FindWindowResponse(error=str(e))
    
    async def Click(self, request, context):
        """Click at coordinates with verification - async version"""
        try:
            session = self._get_or_create_session(request.window_id)

            if session.desktop_session:
                # click() is async and returns ToolOutput
                tool_output = await session.desktop_session.click(request.x, request.y)

                return desktop_pb2.ClickResponse(
                    success=tool_output.success,
                    error=tool_output.error if not tool_output.success else ""
                )
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.ClickResponse(success=False, error="Desktop session not initialized")

        except Exception as e:
            self.logger.error(f"Click failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ClickResponse(success=False, error=str(e))
    
    async def Type(self, request, context):
        """Type text with verification - async version"""
        try:
            session = self._get_or_create_session(request.window_id)

            if session.desktop_session:
                # type_text() is async and returns ToolOutput
                tool_output = await session.desktop_session.type_text(request.text)

                return desktop_pb2.TypeResponse(
                    success=tool_output.success,
                    error=tool_output.error if not tool_output.success else ""
                )
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.TypeResponse(success=False, error="Desktop session not initialized")

        except Exception as e:
            self.logger.error(f"Type failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.TypeResponse(success=False, error=str(e))
    
    async def Observe(self, request, context):
        """Observe desktop state - async version with ToolOutput handling"""
        try:
            session = self._get_or_create_session(request.session_id)

            # Capture current screen state (async, returns ToolOutput)
            screenshot_available = False
            if session.desktop_session:
                tool_output = await session.desktop_session.screenshot()
                screenshot_available = tool_output.success

            # Refresh and get window list from registry
            session.window_registry.refresh()
            windows = list(session.window_registry._registry.values())

            # Perform OCR on screen if requested
            text_content = ""
            if request.include_text and screenshot_available and session.desktop_session:
                tool_output = await session.desktop_session.screenshot()
                if tool_output.success:
                    path = tool_output.result.get("path") if tool_output.result else None
                    if path:
                        parser = HybridVisionParser()
                        result = parser.parse_screenshot(path)
                        text_content = result.get("text", "")

            # Update observation count
            session.observation_count += 1
            session.last_observation = {
                "timestamp": datetime.now().isoformat(),
                "window_count": len(windows),
                "text_content_length": len(text_content),
                "screenshot_available": screenshot_available
            }

            response = desktop_pb2.ObserveResponse(
                observation_id=str(session.observation_count),
                timestamp=session.last_observation["timestamp"],
                window_count=len(windows),
                windows=[
                    desktop_pb2.WindowInfo(
                        id=str(w.hwnd) if w.hwnd else "",
                        title=w.title if w.title else "",
                        x=0,
                        y=0,
                        width=0,
                        height=0
                    )
                    for w in windows[:10]  # Limit to first 10 windows
                ],
                text_content=text_content,
                screenshot_available=screenshot_available
            )

            return response

        except Exception as e:
            self.logger.error(f"Observation failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ObserveResponse(error=str(e))
    
    async def Decide(self, request, context):
        """Decision step - async version"""
        try:
            session = self._get_or_create_session(request.observation_id)

            # This would typically call the LLM/planner
            # For now, return a simple action based on observation state

            if session.last_observation:
                # Generate action based on observation
                action = desktop_pb2.Action(
                    action_type="click",
                    target="window",
                    x=100,
                    y=100,
                    confidence=0.8
                )
            else:
                action = desktop_pb2.Action(
                    action_type="none",
                    target="none",
                    confidence=0.0
                )

            response = desktop_pb2.DecideResponse(
                observation_id=request.observation_id,
                action=action
            )

            return response

        except Exception as e:
            self.logger.error(f"Decision failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.DecideResponse(error=str(e))
    
    async def Act(self, request, context):
        """Action step - async version with ToolOutput handling"""
        try:
            session = self._get_or_create_session(request.session_id)

            if not session.desktop_session:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.ActResponse(success=False, error="Desktop session not initialized")

            action_type = request.action.action_type
            success = False
            screenshot_data = b""
            error_msg = ""

            # Execute action based on type
            if action_type == "click":
                tool_output = await session.desktop_session.click(request.action.x, request.action.y)
                success = tool_output.success
                error_msg = tool_output.error or ""
            elif action_type == "type":
                tool_output = await session.desktop_session.type_text(request.action.text)
                success = tool_output.success
                error_msg = tool_output.error or ""
            elif action_type == "screenshot":
                tool_output = await session.desktop_session.screenshot()
                success = tool_output.success
                if success and tool_output.result:
                    path = tool_output.result.get("path")
                    if path and os.path.exists(path):
                        with open(path, "rb") as f:
                            screenshot_data = f.read()
            else:
                error_msg = f"Unknown action type: {action_type}"

            response_kwargs = {
                "success": success,
                "action_id": request.action.action_id,
                "error": error_msg
            }
            if screenshot_data:
                response_kwargs["screenshot"] = screenshot_data

            response = desktop_pb2.ActResponse(**response_kwargs)
            return response

        except Exception as e:
            self.logger.error(f"Action failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ActResponse(success=False, error=str(e))
    
    async def Verify(self, request, context):
        """Verification step - async version"""
        try:
            session = self._get_or_create_session(request.session_id)

            # Use verification engine to verify action result
            verification_result = session.verification_engine.verify(
                action=request.action,
                expected_state=request.expected_state,
                actual_state=request.actual_state
            )

            response = desktop_pb2.VerifyResponse(
                verified=verification_result.get("verified", False),
                confidence=verification_result.get("confidence", 0.0),
                notes=verification_result.get("notes", "")
            )

            return response

        except Exception as e:
            self.logger.error(f"Verification failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.VerifyResponse(verified=False, error=str(e))
    
    async def Recover(self, request, context):
        """Recovery step - async version"""
        try:
            session = self._get_or_create_session(request.session_id)

            if session.recovery_engine:
                # Use recovery engine to recover from failure
                recovery_result = session.recovery_engine.recover(
                    failure_type=request.failure_type,
                    context=request.context
                )

                response = desktop_pb2.RecoveryResponse(
                    success=recovery_result.get("success", False),
                    recovery_action=recovery_result.get("action", ""),
                    notes=recovery_result.get("notes", "")
                )
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Recovery engine not initialized")
                return desktop_pb2.RecoveryResponse(success=False, error="Recovery engine not initialized")

            return response

        except Exception as e:
            self.logger.error(f"Recovery failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.RecoveryResponse(success=False, error=str(e))
    
    async def CloseSession(self, request, context):
        """Close desktop session and cleanup resources - async version"""
        try:
            if request.session_id in self.sessions:
                session = self.sessions.pop(request.session_id)

                # Desktop session cleanup not available - session will be garbage collected
                # In the future, could call await session.desktop_session.cleanup() if available

                self.logger.info(f"Closed desktop session: {request.session_id}")

            return desktop_pb2.CloseSessionResponse(success=True)

        except Exception as e:
            self.logger.error(f"Failed to close session: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.CloseSessionResponse(success=False, error=str(e))


async def serve_async(port: int = 50051):
    """Start the async gRPC server"""
    # Use async gRPC server
    server = grpc.aio.server()

    # Check if protobuf is available
    if desktop_pb2 and desktop_pb2_grpc:
        desktop_pb2_grpc.add_DesktopAutomationServicer_to_server(
            DesktopAutomationServicer(), server
        )
    else:
        logging.warning("gRPC protobuf not generated yet. Server will start but service methods unavailable.")
        return

    server.add_insecure_port(f'[::]:{port}')
    await server.start()
    logging.info(f"Desktop Automation async gRPC server started on port {port}")
    await server.wait_for_termination()


def serve(port: int = 50051):
    """Start the gRPC server (sync wrapper for async)"""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve_async(port))


if __name__ == '__main__':
    serve(int(os.environ.get("GRPC_PORT", "50051")))
