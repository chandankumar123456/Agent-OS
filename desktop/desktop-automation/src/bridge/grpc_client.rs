// gRPC client for desktop automation bridge
// Connects Rust desktop automation to Python runtime via gRPC

use desktop_protocol::desktop::desktop_automation_client::DesktopAutomationClient;
use desktop_protocol::desktop::*;
use std::time::Duration;
use tokio::time::sleep;
use tonic::{transport::Channel, Code, Status};

/// Error types for gRPC client operations
#[derive(thiserror::Error, Debug)]
pub enum ClientError {
    #[error("Connection failed after {retries} attempts: {source}")]
    ConnectionFailed { retries: u32, source: tonic::transport::Error },
    #[error("Request failed with retry exhaustion: {0}")]
    RequestFailed(#[from] Status),
    #[error("Request timeout after {duration:?}")]
    Timeout { duration: Duration },
    #[error("Server unavailable: {0}")]
    ServerUnavailable(String),
    #[error("Invalid request: {0}")]
    InvalidRequest(String),
}

/// Retry configuration for gRPC operations
#[derive(Clone, Debug)]
pub struct RetryConfig {
    pub max_retries: u32,
    pub initial_backoff: Duration,
    pub max_backoff: Duration,
    pub backoff_multiplier: f64,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_retries: 3,
            initial_backoff: Duration::from_millis(100),
            max_backoff: Duration::from_secs(2),
            backoff_multiplier: 2.0,
        }
    }
}

impl RetryConfig {
    /// Create a new retry configuration with custom settings
    pub fn new(max_retries: u32, initial_backoff_ms: u64) -> Self {
        Self {
            max_retries,
            initial_backoff: Duration::from_millis(initial_backoff_ms),
            max_backoff: Duration::from_secs(2),
            backoff_multiplier: 2.0,
        }
    }

    /// Calculate backoff duration for a given attempt
    pub fn backoff_for_attempt(&self, attempt: u32) -> Duration {
        let backoff_secs = self.initial_backoff.as_secs_f64()
            * self.backoff_multiplier.powi(attempt as i32);
        let backoff = Duration::from_secs_f64(backoff_secs);
        std::cmp::min(backoff, self.max_backoff)
    }
}

/// gRPC client for desktop automation with retry support
#[derive(Clone)]
pub struct DesktopGrpcClient {
    client: DesktopAutomationClient<Channel>,
    retry_config: RetryConfig,
}

impl DesktopGrpcClient {
    /// Connect to the gRPC server at the given address with retry
    pub async fn connect(addr: &str) -> Result<Self, ClientError> {
        let config = RetryConfig::default();
        Self::connect_with_retry(addr, &config).await
    }

    /// Connect to the gRPC server with custom retry configuration
    pub async fn connect_with_retry(
        addr: &str,
        config: &RetryConfig,
    ) -> Result<Self, ClientError> {
        let mut last_error = None;

        for attempt in 0..=config.max_retries {
            match DesktopAutomationClient::connect(addr.to_string()).await {
                Ok(client) => {
                    return Ok(Self {
                        client,
                        retry_config: config.clone(),
                    });
                }
                Err(e) => {
                    last_error = Some(e);
                    if attempt < config.max_retries {
                        let backoff = config.backoff_for_attempt(attempt);
                        sleep(backoff).await;
                    }
                }
            }
        }

        Err(ClientError::ConnectionFailed {
            retries: config.max_retries,
            source: last_error.unwrap(),
        })
    }

    /// Determine if a gRPC error is retryable
    fn is_retryable_error(status: &Status) -> bool {
        matches!(
            status.code(),
            Code::Unavailable
                | Code::DeadlineExceeded
                | Code::ResourceExhausted
                | Code::Aborted
        )
    }

    /// Health check - ping the gRPC server
    pub async fn health_check(&mut self) -> Result<bool, ClientError> {
        // Use observe as a simple health check with a short timeout
        let result = tokio::time::timeout(
            Duration::from_secs(5),
            self.observe("health-check", false),
        )
        .await;

        match result {
            Ok(Ok(_)) => Ok(true),
            Ok(Err(error)) => Err(error),
            Err(_) => Err(ClientError::Timeout {
                duration: Duration::from_secs(5),
            }),
        }
    }

    /// Capture a screen region with retry
    pub async fn capture_screen(
        &mut self,
        window_id: &str,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
    ) -> Result<ScreenCaptureResponse, ClientError> {
        let window_id = window_id.to_string();
        let mut last_status = None;

        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(ScreenCaptureRequest {
                window_id: window_id.clone(),
                x,
                y,
                width,
                height,
            });
            match self.client.screen_capture(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Perform OCR on screen with retry
    pub async fn ocr_screen(
        &mut self,
        image_data: Vec<u8>,
        language: &str,
        preprocess: bool,
    ) -> Result<OcrScreenResponse, ClientError> {
        let language = language.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(OcrScreenRequest {
                image_data: image_data.clone(),
                language: language.clone(),
                preprocess,
            });
            match self.client.ocr_screen(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Find a window by title with retry
    pub async fn find_window(
        &mut self,
        title: &str,
        class_name: &str,
        partial_match: bool,
    ) -> Result<FindWindowResponse, ClientError> {
        let title = title.to_string();
        let class_name = class_name.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(FindWindowRequest {
                title: title.clone(),
                class_name: class_name.clone(),
                partial_match,
            });
            match self.client.find_window(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Click at coordinates with retry
    pub async fn click(
        &mut self,
        window_id: &str,
        x: i32,
        y: i32,
    ) -> Result<ClickResponse, ClientError> {
        let window_id = window_id.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(ClickRequest {
                window_id: window_id.clone(),
                x,
                y,
            });
            match self.client.click(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Type text with retry
    pub async fn type_text(
        &mut self,
        window_id: &str,
        text: &str,
    ) -> Result<TypeResponse, ClientError> {
        let window_id = window_id.to_string();
        let text = text.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(TypeRequest {
                window_id: window_id.clone(),
                text: text.clone(),
            });
            match self.client.r#type(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Observe desktop state with retry
    pub async fn observe(
        &mut self,
        session_id: &str,
        include_text: bool,
    ) -> Result<ObserveResponse, ClientError> {
        let session_id = session_id.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(ObserveRequest {
                session_id: session_id.clone(),
                include_text,
            });
            match self.client.observe(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Make decision based on observation with retry
    pub async fn decide(
        &mut self,
        observation_id: &str,
    ) -> Result<DecideResponse, ClientError> {
        let observation_id = observation_id.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(DecideRequest {
                observation_id: observation_id.clone(),
            });
            match self.client.decide(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Execute action with retry
    pub async fn act(
        &mut self,
        session_id: &str,
        action: Action,
    ) -> Result<ActResponse, ClientError> {
        let session_id = session_id.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(ActRequest {
                session_id: session_id.clone(),
                action: Some(action.clone()),
            });
            match self.client.act(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Verify action result with retry
    pub async fn verify(
        &mut self,
        session_id: &str,
        action: Action,
        expected_state: &str,
        actual_state: &str,
    ) -> Result<VerifyResponse, ClientError> {
        let session_id = session_id.to_string();
        let expected_state = expected_state.to_string();
        let actual_state = actual_state.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(VerifyRequest {
                session_id: session_id.clone(),
                action: Some(action.clone()),
                expected_state: expected_state.clone(),
                actual_state: actual_state.clone(),
            });
            match self.client.verify(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Recover from failure with retry
    pub async fn recover(
        &mut self,
        session_id: &str,
        failure_type: &str,
        context: &str,
    ) -> Result<RecoveryResponse, ClientError> {
        let session_id = session_id.to_string();
        let failure_type = failure_type.to_string();
        let context = context.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(RecoverRequest {
                session_id: session_id.clone(),
                failure_type: failure_type.clone(),
                context: context.clone(),
            });
            match self.client.recover(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
    }

    /// Close session with retry
    pub async fn close_session(
        &mut self,
        session_id: &str,
    ) -> Result<CloseSessionResponse, ClientError> {
        let session_id = session_id.to_string();
        let mut last_status = None;
        for attempt in 0..=self.retry_config.max_retries {
            let request = tonic::Request::new(CloseSessionRequest {
                session_id: session_id.clone(),
            });
            match self.client.close_session(request).await {
                Ok(resp) => return Ok(resp.into_inner()),
                Err(status) => {
                    last_status = Some(status.clone());
                    if !Self::is_retryable_error(&status) {
                        return Err(ClientError::RequestFailed(status));
                    }
                    if attempt < self.retry_config.max_retries {
                        sleep(self.retry_config.backoff_for_attempt(attempt)).await;
                    }
                }
            }
        }
        Err(ClientError::RequestFailed(last_status.unwrap()))
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
