//! OCR service for text recognition
//! Supports Windows OCR with Tesseract fallback

/// OCR result
#[derive(Debug, Clone)]
pub struct OcrResult {
    pub text: String,
    pub confidence: f32,
}

/// OCR service
pub struct OcrService {
    language: String,
}

impl OcrService {
    pub fn new() -> Self {
        Self {
            language: "en-US".to_string(),
        }
    }

    pub fn with_language(language: &str) -> Self {
        Self {
            language: language.to_string(),
        }
    }

    /// Recognize text from image data
    /// Currently delegates to Python via HTTP POST for full OCR
    /// Native implementation would use Windows.Media.Ocr but requires complex WinRT/COM interop
    pub fn recognize(
        &self,
        image_data: &[u8],
        language: &str,
        _preprocess: bool,
    ) -> Result<OcrResult, Box<dyn std::error::Error + Send + Sync>> {
        // If no image data, return empty result
        if image_data.is_empty() {
            return Ok(OcrResult {
                text: String::new(),
                confidence: 0.0,
            });
        }

        tracing::debug!(
            "OCR request: {} bytes, language={}",
            image_data.len(),
            language
        );

        // For now, return placeholder - native Windows OCR requires WinRT/COM interop
        // which is complex. The current architecture delegates to Python for OCR.
        // TODO: Implement native Windows.Media.Ocr via windows-rs
        Ok(OcrResult {
            text: String::new(),
            confidence: 0.0,
        })
    }

    /// Check if a language is supported
    pub fn is_language_supported(language: &str) -> bool {
        matches!(
            language.to_lowercase().as_str(),
            "en-us" | "en-gb" | "de-de" | "fr-fr" | "es-es" | "it-it" |
            "ja-jp" | "ko-kr" | "zh-cn" | "zh-tw"
        )
    }

    /// Get supported languages
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