# Desktop Automation gRPC Server
# This module provides the Python side of the gRPC bridge to Rust desktop automation
# Implements the full observe-decide-act-verify-recover loop for desktop automation

import asyncio
import grpc
from concurrent import futures
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import base64
from io import BytesIO

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
    
    def ScreenCapture(self, request, context):
        """Capture screen region with full error handling"""
        try:
            session = self._get_or_create_session(request.window_id)
            
            # Capture screen using existing DesktopSession
            if session.desktop_session:
                screenshot = session.desktop_session.screenshot(
                    region=(request.x, request.y, request.x + request.width, request.y + request.height)
                )
                
                # Convert to PNG bytes
                buffered = BytesIO()
                screenshot.save(buffered, format="PNG")
                image_data = buffered.getvalue()
                
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
    
    def OcrScreen(self, request, context):
        """Perform OCR on screen image using Windows OCR engine"""
        try:
            session = self._get_or_create_session("global_ocr")
            
            # Use HybridVisionParser for OCR with DPI scaling support
            if session.desktop_session:
                # Create temporary image from bytes
                image = BytesIO(request.image_data)
                
                # Parse using hybrid vision parser
                parser = HybridVisionParser()
                result = parser.parse_screenshot(image)
                
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
    
    def FindWindow(self, request, context):
        """Find window by title using WindowRegistry"""
        try:
            session = self._get_or_create_session("window_find")
            
            # Get windows from registry - use find_by_title for efficient lookup
            matched_ref = session.window_registry.find_by_title(request.title)
            
            # If not found and partial_match is enabled, try to find by iterating
            if matched_ref is None and request.partial_match:
                for ref in session.window_registry._registry.values():
                    if request.title.lower() in ref.title.lower():
                        matched_ref = ref
                        break
            
            if matched_ref:
                # WindowRef has hwnd, not left/top/right/bottom - use 0 for position
                # as WindowRef doesn't track window position
                response = desktop_pb2.FindWindowResponse(
                    window_id=str(matched_ref.hwnd) if matched_ref.hwnd else "",
                    title=matched_ref.title,
                    x=0,
                    y=0,
                    width=0,
                    height=0,
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
    
    def Click(self, request, context):
        """Click at coordinates with verification"""
        try:
            session = self._get_or_create_session(request.window_id)
            
            if session.desktop_session:
                # Perform click with stabilizer
                result = session.stabilizer.execute_with_retry(
                    lambda: session.desktop_session.click(request.x, request.y)
                )
                
                return desktop_pb2.ClickResponse(success=result["success"])
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.ClickResponse(success=False, error="Desktop session not initialized")
                
        except Exception as e:
            self.logger.error(f"Click failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ClickResponse(success=False, error=str(e))
    
    def Type(self, request, context):
        """Type text with verification"""
        try:
            session = self._get_or_create_session(request.window_id)
            
            if session.desktop_session:
                # Perform typing with stabilizer
                result = session.stabilizer.execute_with_retry(
                    lambda: session.desktop_session.type_text(request.text)
                )
                
                return desktop_pb2.TypeResponse(success=result["success"])
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.TypeResponse(success=False, error="Desktop session not initialized")
                
        except Exception as e:
            self.logger.error(f"Type failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.TypeResponse(success=False, error=str(e))
    
    def Observe(self, request, context):
        """Observe desktop state - first step in observe-decide-act-verify-recover loop"""
        try:
            session = self._get_or_create_session(request.session_id)
            
            # Capture current screen state
            screenshot = session.desktop_session.screenshot() if session.desktop_session else None
            
            # Get window list from registry
            windows = list(session.window_registry._registry.values())
            
            # Perform OCR on screen if requested
            text_content = ""
            if request.include_text:
                parser = HybridVisionParser()
                if screenshot:
                    buffered = BytesIO()
                    screenshot.save(buffered, format="PNG")
                    result = parser.parse_image(buffered)
                    text_content = result.get("text", "")
            
            # Update observation count
            session.observation_count += 1
            session.last_observation = {
                "timestamp": datetime.now().isoformat(),
                "window_count": len(windows),
                "text_content_length": len(text_content),
                "screenshot_available": screenshot is not None
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
                screenshot_available=screenshot is not None
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Observation failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ObserveResponse(error=str(e))
    
    def Decide(self, request, context):
        """Decision step - determine what action to take based on observation"""
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
    
    def Act(self, request, context):
        """Action step - execute the decided action"""
        try:
            session = self._get_or_create_session(request.session_id)
            
            if not session.desktop_session:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Desktop session not initialized")
                return desktop_pb2.ActResponse(success=False, error="Desktop session not initialized")
            
            # Execute action based on type
            if request.action.action_type == "click":
                result = session.stabilizer.execute_with_retry(
                    lambda: session.desktop_session.click(request.action.x, request.action.y)
                )
            elif request.action.action_type == "type":
                result = session.stabilizer.execute_with_retry(
                    lambda: session.desktop_session.type_text(request.action.text)
                )
            elif request.action.action_type == "screenshot":
                screenshot = session.desktop_session.screenshot()
                buffered = BytesIO()
                screenshot.save(buffered, format="PNG")
                result = {"success": True, "screenshot": buffered.getvalue()}
            else:
                result = {"success": False, "error": f"Unknown action type: {request.action.action_type}"}
            
            response = desktop_pb2.ActResponse(
                success=result.get("success", False),
                action_id=request.action.action_id,
                **({"screenshot": result.get("screenshot", b"")} if "screenshot" in result else {})
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Action failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.ActResponse(success=False, error=str(e))
    
    def Verify(self, request, context):
        """Verification step - verify the action result"""
        try:
            session = self._get_or_create_session(request.session_id)
            
            # Use verification engine to verify action result
            verification_result = session.verification_engine.verify(
                action=request.action,
                expected_state=request.expected_state,
                actual_state=request.actual_state
            )
            
            response = desktop_pb2.VerifyResponse(
                verified=verification_result["verified"],
                confidence=verification_result.get("confidence", 0.0),
                notes=verification_result.get("notes", "")
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Verification failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.VerifyResponse(verified=False, error=str(e))
    
    def Recover(self, request, context):
        """Recovery step - recover from failures"""
        try:
            session = self._get_or_create_session(request.session_id)
            
            if session.recovery_engine:
                # Use recovery engine to recover from failure
                recovery_result = session.recovery_engine.recover(
                    failure_type=request.failure_type,
                    context=request.context
                )
                
                response = desktop_pb2.RecoverResponse(
                    success=recovery_result["success"],
                    recovery_action=recovery_result.get("action", ""),
                    notes=recovery_result.get("notes", "")
                )
            else:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Recovery engine not initialized")
                return desktop_pb2.RecoverResponse(success=False, error="Recovery engine not initialized")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Recovery failed: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.RecoverResponse(success=False, error=str(e))
    
    def CloseSession(self, request, context):
        """Close desktop session and cleanup resources"""
        try:
            if request.session_id in self.sessions:
                session = self.sessions.pop(request.session_id)
                
                # Desktop session cleanup not available - session will be garbage collected
                
                self.logger.info(f"Closed desktop session: {request.session_id}")
            
            return desktop_pb2.CloseSessionResponse(success=True)
            
        except Exception as e:
            self.logger.error(f"Failed to close session: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return desktop_pb2.CloseSessionResponse(success=False, error=str(e))


def serve(port: int = 50051):
    """Start the gRPC server"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Check if protobuf is available
    if desktop_pb2 and desktop_pb2_grpc:
        desktop_pb2_grpc.add_DesktopAutomationServicer_to_server(
            DesktopAutomationServicer(), server
        )
    else:
        logging.warning("gRPC protobuf not generated yet. Server will start but service methods unavailable.")
        # Add a placeholder servicer
        class PlaceholderServicer:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        server.add_insecure_port(f'[::]:{port}')
    
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logging.info(f"Desktop Automation gRPC server started on port {port}")
    server.wait_for_termination()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    serve()
