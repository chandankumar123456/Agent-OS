//! OCR service for text recognition
//!
//! Delegates actual OCR operations to the Python gRPC server (which uses pytesseract).
//! The Python desktop automation server runs on port 50051 and provides real OCR.
//! Native Windows OCR (Windows.Media.Ocr) requires complex WinRT/COM interop
//! and is not yet implemented - the Python gRPC delegation is the production path.

use std::sync::Mutex;

use crate::bridge::grpc_client::DesktopGrpcClient;

/// OCR result
#[derive(Debug, Clone)]
pub struct OcrResult {
    pub text: String,
    pub confidence: f32,
}

/// OCR service
pub struct OcrService {
    language: String,
    grpc_addr: String,
    client: Mutex<Option<DesktopGrpcClient>>,
}

impl OcrService {
    pub fn new() -> Self {
        Self {
            language: "en-US".to_string(),
            grpc_addr: "http://127.0.0.1:50051".to_string(),
            client: Mutex::new(None),
        }
    }

    pub fn with_language(language: &str) -> Self {
        Self {
            language: language.to_string(),
            grpc_addr: "http://127.0.0.1:50051".to_string(),
            client: Mutex::new(None),
        }
    }

    /// Set the gRPC server address for Python delegate calls
    #[allow(dead_code)]
    pub fn with_grpc_addr(mut self, addr: &str) -> Self {
        self.grpc_addr = addr.to_string();
        self
    }

    /// Get or create the gRPC client to the Python desktop server
    fn get_client(&self) -> Option<DesktopGrpcClient> {
        let mut guard = self.client.lock().unwrap();
        if guard.is_some() {
            return guard.clone();
        }
        // Try to connect - this is a best-effort delegation.
        // If Python gRPC is not available, we return empty results.
        let rt = match tokio::runtime::Runtime::new() {
            Ok(r) => r,
            Err(_) => return None,
        };
        match rt.block_on(DesktopGrpcClient::connect(&self.grpc_addr)) {
            Ok(client) => {
                tracing::info!("Connected to Python OCR gRPC server at {}", self.grpc_addr);
                *guard = Some(client.clone());
                Some(client)
            }
            Err(e) => {
                tracing::warn!(
                    "Failed to connect to Python OCR gRPC server at {}: {}",
                    self.grpc_addr,
                    e
                );
                None
            }
        }
    }

    /// Recognize text from image data
    ///
    /// Delegates to the Python gRPC server for actual OCR via pytesseract.
    /// Falls back to empty result if Python server is not available.
    pub fn recognize(
        &self,
        image_data: &[u8],
        language: &str,
        preprocess: bool,
    ) -> Result<OcrResult, Box<dyn std::error::Error + Send + Sync>> {
        let effective_language = if language.is_empty() || language == "auto" {
            &self.language
        } else {
            language
        };

        if image_data.is_empty() {
            return Ok(OcrResult {
                text: String::new(),
                confidence: 0.0,
            });
        }

        tracing::debug!(
            "OCR request: {} bytes, language={}",
            image_data.len(),
            effective_language
        );

        // Try Python gRPC delegation
        if let Some(mut client) = self.get_client() {
            let rt = match tokio::runtime::Runtime::new() {
                Ok(r) => r,
                Err(e) => {
                    tracing::warn!("Failed to create tokio runtime for OCR: {}", e);
                    return Ok(OcrResult {
                        text: String::new(),
                        confidence: 0.0,
                    });
                }
            };
            match rt.block_on(client.ocr_screen(image_data.to_vec(), effective_language, preprocess))
            {
                Ok(resp) => {
                    if !resp.text.is_empty() {
                        tracing::debug!(
                            "OCR via Python gRPC: text={}, confidence={}",
                            resp.text.len(),
                            resp.confidence
                        );
                        return Ok(OcrResult {
                            text: resp.text,
                            confidence: resp.confidence,
                        });
                    }
                }
                Err(e) => {
                    tracing::warn!("Python gRPC OCR failed: {}", e);
                }
            }
        }

        // Fallback: try native Windows OCR via Media.Ocr (WinRT)
        #[cfg(target_os = "windows")]
        {
            match self.try_windows_ocr(image_data, effective_language) {
                Ok(Some(result)) => return Ok(result),
                Ok(None) => {} // Continue to empty result
                Err(e) => {
                    tracing::warn!("Windows OCR failed: {}", e);
                }
            }
        }

        tracing::warn!("OCR unavailable - no Python gRPC server and no native OCR engine");
        Ok(OcrResult {
            text: String::new(),
            confidence: 0.0,
        })
    }

    /// Try native Windows OCR via Media.Ocr (WinRT)
    /// This is a best-effort implementation that may not compile on all Windows targets.
    #[cfg(target_os = "windows")]
    fn try_windows_ocr(
        &self,
        _image_data: &[u8],
        _language: &str,
    ) -> Result<Option<OcrResult>, Box<dyn std::error::Error + Send + Sync>> {
        // Windows.Media.Ocr via winrt requires complex COM initialization.
        // For now, this is a placeholder. The recommended path is Python gRPC delegation.
        Ok(None)
    }

    /// Check if a language is supported
    #[allow(dead_code)]
    pub fn is_language_supported(language: &str) -> bool {
        matches!(
            language.to_lowercase().as_str(),
            "en-us"
                | "en-gb"
                | "de-de"
                | "fr-fr"
                | "es-es"
                | "it-it"
                | "ja-jp"
                | "ko-kr"
                | "zh-cn"
                | "zh-tw"
        )
    }

    /// Get supported languages
    #[allow(dead_code)]
    pub fn get_supported_languages() -> Vec<String> {
        vec![
            "en-US".to_string(),
            "en-GB".to_string(),
            "de-DE".to_string(),
            "fr-FR".to_string(),
            "es-ES".to_string(),
            "it-IT".to_string(),
            "ja-JP".to_string(),
            "ko-KR".to_string(),
            "zh-CN".to_string(),
            "zh-TW".to_string(),
        ]
    }
}

impl Default for OcrService {
    fn default() -> Self {
        Self::new()
    }
}
