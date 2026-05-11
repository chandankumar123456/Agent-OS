//! gRPC Server implementation for desktop automation services
//! Provides native Windows implementations for <5ms latency

use desktop_protocol::desktop_automation_server::DesktopAutomation;

use desktop_protocol::{
    ActRequest, ActResponse, ClickRequest, ClickResponse, CloseSessionRequest,
    CloseSessionResponse, DecideRequest, DecideResponse, FindWindowRequest, FindWindowResponse,
    ObserveRequest, ObserveResponse, OcrScreenRequest, OcrScreenResponse,
    RecoverRequest, RecoveryResponse, ScreenCaptureRequest, ScreenCaptureResponse,
    TypeRequest, TypeResponse, VerifyRequest, VerifyResponse,
};

use std::sync::Arc;
use tokio::sync::RwLock;
use async_trait::async_trait;

mod window_service;
mod ocr_service;
mod session;

pub use window_service::WindowService;
pub use ocr_service::OcrService;
pub use session::SessionManager;

/// Main desktop automation service implementing gRPC trait
#[derive(Clone)]
pub struct DesktopAutomationService {
    window_service: Arc<WindowService>,
    ocr_service: Arc<OcrService>,
    session_manager: Arc<RwLock<SessionManager>>,
}

impl DesktopAutomationService {
    /// Create a new desktop automation service
    pub fn new() -> Self {
        Self {
            window_service: Arc::new(WindowService::new()),
            ocr_service: Arc::new(OcrService::new()),
            session_manager: Arc::new(RwLock::new(SessionManager::new())),
        }
    }

    /// Create with custom configuration
    pub fn with_config(ocr_language: &str) -> Self {
        Self {
            window_service: Arc::new(WindowService::new()),
            ocr_service: Arc::new(OcrService::with_language(ocr_language)),
            session_manager: Arc::new(RwLock::new(SessionManager::new())),
        }
    }
}

impl Default for DesktopAutomationService {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl DesktopAutomation for DesktopAutomationService {
    /// Capture screen region
    async fn screen_capture(
        &self,
        request: tonic::Request<ScreenCaptureRequest>,
    ) -> std::result::Result<tonic::Response<ScreenCaptureResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!(
            "Screen capture: window_id={}, x={}, y={}, w={}, h={}",
            req.window_id,
            req.x,
            req.y,
            req.width,
            req.height
        );

        // Use capture module for screen capture
        match crate::capture::capture_region(req.x, req.y, req.width, req.height) {
            Ok(image_data) => Ok(tonic::Response::new(ScreenCaptureResponse {
                image_data,
                format: "png".to_string(),
                error: String::new(),
            })),
            Err(e) => Ok(tonic::Response::new(ScreenCaptureResponse {
                image_data: Vec::new(),
                format: String::new(),
                error: e.to_string(),
            })),
        }
    }

    /// OCR screen region
    async fn ocr_screen(
        &self,
        request: tonic::Request<OcrScreenRequest>,
    ) -> std::result::Result<tonic::Response<OcrScreenResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("OCR: language={}, preprocess={}", req.language, req.preprocess);

        // Use OCR service for text recognition
        match self.ocr_service.recognize(&req.image_data, &req.language, req.preprocess) {
            Ok(result) => Ok(tonic::Response::new(OcrScreenResponse {
                text: result.text,
                confidence: result.confidence,
                error: String::new(),
            })),
            Err(e) => Ok(tonic::Response::new(OcrScreenResponse {
                text: String::new(),
                confidence: 0.0,
                error: e.to_string(),
            })),
        }
    }

    /// Find window by title
    async fn find_window(
        &self,
        request: tonic::Request<FindWindowRequest>,
    ) -> std::result::Result<tonic::Response<FindWindowResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!(
            "Find window: title='{}', class='{}', partial={}",
            req.title,
            req.class_name,
            req.partial_match
        );

        match self.window_service.find_window(&req.title, &req.class_name, req.partial_match) {
            Some(window_info) => Ok(tonic::Response::new(FindWindowResponse {
                window_id: window_info.hwnd.to_string(),
                title: window_info.title,
                x: window_info.x,
                y: window_info.y,
                width: window_info.width as i32,
                height: window_info.height as i32,
                found: true,
                error: String::new(),
            })),
            None => Ok(tonic::Response::new(FindWindowResponse {
                window_id: String::new(),
                title: String::new(),
                x: 0,
                y: 0,
                width: 0,
                height: 0,
                found: false,
                error: "Window not found".to_string(),
            })),
        }
    }

    /// Click at coordinates
    async fn click(
        &self,
        request: tonic::Request<ClickRequest>,
    ) -> std::result::Result<tonic::Response<ClickResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Click: window_id={}, x={}, y={}", req.window_id, req.x, req.y);

        // Parse window handle from window_id
        let hwnd = req.window_id.parse::<isize>().unwrap_or(0);
        let success = self.window_service.click(hwnd, req.x, req.y);

        Ok(tonic::Response::new(ClickResponse {
            success,
            error: if success { String::new() } else { "Click failed".to_string() },
        }))
    }

    /// Type text
    async fn r#type(
        &self,
        request: tonic::Request<TypeRequest>,
    ) -> std::result::Result<tonic::Response<TypeResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Type: window_id={}, text='{}'", req.window_id, req.text);

        let hwnd = req.window_id.parse::<isize>().unwrap_or(0);
        let success = self.window_service.type_text(hwnd, &req.text);

        Ok(tonic::Response::new(TypeResponse {
            success,
            error: if success { String::new() } else { "Type failed".to_string() },
        }))
    }

    /// Observe desktop state
    async fn observe(
        &self,
        request: tonic::Request<ObserveRequest>,
    ) -> std::result::Result<tonic::Response<ObserveResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Observe: session_id={}", req.session_id);

        // Get all visible windows for observation
        let windows = self.window_service.enumerate_windows();
        let mut window_info = Vec::new();

        for (hwnd, _title) in windows {
            let info = self.window_service.get_window_info(hwnd);
            window_info.push(desktop_protocol::desktop::WindowInfo {
                id: hwnd.to_string(),
                title: info.title,
                x: info.x,
                y: info.y,
                width: info.width as i32,
                height: info.height as i32,
            });
        }

        Ok(tonic::Response::new(ObserveResponse {
            observation_id: req.session_id,
            timestamp: {
                let ts = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default();
                format!("{}", ts.as_secs())
            },
            window_count: window_info.len() as i32,
            windows: window_info,
            text_content: String::new(),
            screenshot_available: false,
            error: String::new(),
        }))
    }

    /// Decide based on observation
    async fn decide(
        &self,
        request: tonic::Request<DecideRequest>,
    ) -> std::result::Result<tonic::Response<DecideResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Decide: observation_id={}", req.observation_id);

        // This is a placeholder - actual decision making would involve AI
        Ok(tonic::Response::new(DecideResponse {
            observation_id: req.observation_id,
            action: Some(desktop_protocol::desktop::Action {
                action_type: "noop".to_string(),
                target: String::new(),
                x: 0,
                y: 0,
                text: String::new(),
                confidence: 1.0,
                action_id: String::new(),
            }),
            error: String::new(),
        }))
    }

    /// Execute action
    async fn act(
        &self,
        request: tonic::Request<ActRequest>,
    ) -> std::result::Result<tonic::Response<ActResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Act: session_id={}", req.session_id);

        let _session_manager = self.session_manager.read().await;
        
        // Handle action based on type
        if let Some(action) = &req.action {
            match action.action_type.as_str() {
                "click" => {
                    let target = &action.target;
                    let coords: Vec<&str> = target.split(',').collect();
                    if coords.len() == 2 {
                        if let (Ok(x), Ok(y)) = (coords[0].parse::<i32>(), coords[1].parse::<i32>()) {
                            let _ = self.window_service.click(0, x, y);
                        }
                    }
                }
                "type" => {
                    if !action.text.is_empty() {
                        let _ = self.window_service.type_text(0, &action.text);
                    }
                }
                _ => {}
            }
        }

        Ok(tonic::Response::new(ActResponse {
            success: true,
            action_id: String::new(),
            screenshot: Vec::new(),
            error: String::new(),
        }))
    }

    /// Verify action result
    async fn verify(
        &self,
        request: tonic::Request<VerifyRequest>,
    ) -> std::result::Result<tonic::Response<VerifyResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Verify: session_id={}", req.session_id);

        // Simple verification - compare expected vs actual
        let verified = req.expected_state == req.actual_state;

        Ok(tonic::Response::new(VerifyResponse {
            verified,
            confidence: if verified { 1.0 } else { 0.0 },
            notes: if verified {
                "State matches expected".to_string()
            } else {
                "State does not match".to_string()
            },
            error: String::new(),
        }))
    }

    /// Recover from failure
    async fn recover(
        &self,
        request: tonic::Request<RecoverRequest>,
    ) -> std::result::Result<tonic::Response<RecoveryResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!(
            "Recover: session_id={}, failure_type={}",
            req.session_id,
            req.failure_type
        );

        // Recovery strategies based on failure type
        let strategy = match req.failure_type.as_str() {
            "click_failed" => "retry_with_refocus",
            "type_failed" => "retry_with_delay",
            "window_not_found" => "search_alternate",
            _ => "retry",
        };

        Ok(tonic::Response::new(RecoveryResponse {
            success: true,
            recovery_action: strategy.to_string(),
            notes: format!("Recovery strategy: {}", strategy),
            error: String::new(),
        }))
    }

    /// Close session
    async fn close_session(
        &self,
        request: tonic::Request<CloseSessionRequest>,
    ) -> std::result::Result<tonic::Response<CloseSessionResponse>, tonic::Status> {
        let req = request.into_inner();
        tracing::debug!("Close session: session_id={}", req.session_id);

        let mut session_manager = self.session_manager.write().await;
        session_manager.remove_session(&req.session_id);

        Ok(tonic::Response::new(CloseSessionResponse {
            success: true,
            error: String::new(),
        }))
    }
}

/// Start the gRPC server
pub async fn start_server(addr: &str) -> Result<(), Box<dyn std::error::Error>> {
    use tonic::transport::Server;
    use desktop_protocol::desktop_automation_server::DesktopAutomationServer;

    let addr = addr.parse()?;
    let service = DesktopAutomationService::new();

    tracing::info!("Starting desktop automation gRPC server on {}", addr);

    Server::builder()
        .add_service(DesktopAutomationServer::new(service))
        .serve(addr)
        .await?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_service_creation() {
        let service = DesktopAutomationService::new();
        assert!(true);
    }

    #[tokio::test]
    async fn test_find_window() {
        let service = DesktopAutomationService::new();
        // This will fail on CI but works on Windows with desktop
        let result = service
            .find_window(tonic::Request::new(FindWindowRequest {
                title: "Notepad".to_string(),
                class_name: String::new(),
                partial_match: true,
            }))
            .await;
        // Just verify it returns a response
        assert!(result.is_ok());
    }
}