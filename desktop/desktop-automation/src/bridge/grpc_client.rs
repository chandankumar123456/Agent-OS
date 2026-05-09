// gRPC client for desktop automation bridge
// Connects Rust desktop automation to Python runtime via gRPC

use desktop_protocol::desktop::desktop_automation_client::DesktopAutomationClient;
use desktop_protocol::desktop::*;
use tonic::{transport::Channel, Status};

/// gRPC client for desktop automation
pub struct DesktopGrpcClient {
    client: DesktopAutomationClient<Channel>,
}

impl DesktopGrpcClient {
    /// Connect to the gRPC server at the given address
    pub async fn connect(addr: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let client = DesktopAutomationClient::connect(addr.to_string()).await?;
        Ok(Self { client })
    }

    /// Capture a screen region
    pub async fn capture_screen(
        &mut self,
        window_id: &str,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    ) -> Result<ScreenCaptureResponse, Status> {
        let request = tonic::Request::new(ScreenCaptureRequest {
            window_id: window_id.to_string(),
            x,
            y,
            width,
            height,
        });
        let response = self.client.screen_capture(request).await?;
        Ok(response.into_inner())
    }

    /// Perform OCR on screen
    pub async fn ocr_screen(
        &mut self,
        image_data: Vec<u8>,
        language: &str,
        preprocess: bool,
    ) -> Result<OcrScreenResponse, Status> {
        let request = tonic::Request::new(OcrScreenRequest {
            image_data,
            language: language.to_string(),
            preprocess,
        });
        let response = self.client.ocr_screen(request).await?;
        Ok(response.into_inner())
    }

    /// Find a window by title
    pub async fn find_window(
        &mut self,
        title: &str,
        class_name: &str,
        partial_match: bool,
    ) -> Result<FindWindowResponse, Status> {
        let request = tonic::Request::new(FindWindowRequest {
            title: title.to_string(),
            class_name: class_name.to_string(),
            partial_match,
        });
        let response = self.client.find_window(request).await?;
        Ok(response.into_inner())
    }

    /// Click at coordinates
    pub async fn click(
        &mut self,
        window_id: &str,
        x: i32,
        y: i32,
    ) -> Result<ClickResponse, Status> {
        let request = tonic::Request::new(ClickRequest {
            window_id: window_id.to_string(),
            x,
            y,
        });
        let response = self.client.click(request).await?;
        Ok(response.into_inner())
    }

    /// Type text
    pub async fn type_text(
        &mut self,
        window_id: &str,
        text: &str,
    ) -> Result<TypeResponse, Status> {
        let request = tonic::Request::new(TypeRequest {
            window_id: window_id.to_string(),
            text: text.to_string(),
        });
        let response = self.client.r#type(request).await?;
        Ok(response.into_inner())
    }

    /// Observe desktop state
    pub async fn observe(
        &mut self,
        session_id: &str,
        include_text: bool,
    ) -> Result<ObserveResponse, Status> {
        let request = tonic::Request::new(ObserveRequest {
            session_id: session_id.to_string(),
            include_text,
        });
        let response = self.client.observe(request).await?;
        Ok(response.into_inner())
    }

    /// Make decision based on observation
    pub async fn decide(
        &mut self,
        observation_id: &str,
    ) -> Result<DecideResponse, Status> {
        let request = tonic::Request::new(DecideRequest {
            observation_id: observation_id.to_string(),
        });
        let response = self.client.decide(request).await?;
        Ok(response.into_inner())
    }

    /// Execute action
    pub async fn act(
        &mut self,
        session_id: &str,
        action: Action,
    ) -> Result<ActResponse, Status> {
        let request = tonic::Request::new(ActRequest {
            session_id: session_id.to_string(),
            action: Some(action),
        });
        let response = self.client.act(request).await?;
        Ok(response.into_inner())
    }

    /// Verify action result
    pub async fn verify(
        &mut self,
        session_id: &str,
        action: Action,
        expected_state: &str,
        actual_state: &str,
    ) -> Result<VerifyResponse, Status> {
        let request = tonic::Request::new(VerifyRequest {
            session_id: session_id.to_string(),
            action: Some(action),
            expected_state: expected_state.to_string(),
            actual_state: actual_state.to_string(),
        });
        let response = self.client.verify(request).await?;
        Ok(response.into_inner())
    }

    /// Recover from failure
    pub async fn recover(
        &mut self,
        session_id: &str,
        failure_type: &str,
        context: &str,
    ) -> Result<RecoveryResponse, Status> {
        let request = tonic::Request::new(RecoverRequest {
            session_id: session_id.to_string(),
            failure_type: failure_type.to_string(),
            context: context.to_string(),
        });
        let response = self.client.recover(request).await?;
        Ok(response.into_inner())
    }

    /// Close session
    pub async fn close_session(
        &mut self,
        session_id: &str,
    ) -> Result<CloseSessionResponse, Status> {
        let request = tonic::Request::new(CloseSessionRequest {
            session_id: session_id.to_string(),
        });
        let response = self.client.close_session(request).await?;
        Ok(response.into_inner())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Note: These tests require a running gRPC server
    // Run with: cargo test -- --ignored

    #[tokio::test]
    #[ignore = "Requires running gRPC server"]
    async fn test_connect() {
        let result = DesktopGrpcClient::connect("http://localhost:50051").await;
        assert!(result.is_ok());
    }
}
