use std::error::Error;

/// Windows OCR engine placeholder
/// Full WinRT implementation requires complex COM/WinRT setup
/// For production use, OCR is performed via Python gRPC server
pub struct OcrEngine;

impl OcrEngine {
    /// Create a new OCR engine
    pub fn new() -> Result<Self, Box<dyn Error>> {
        tracing::info!("OCR engine initialized (Python-side OCR via gRPC)");
        Ok(Self)
    }

    /// Create OCR engine for a specific language
    pub fn with_language(_language_tag: &str) -> Result<Self, Box<dyn Error>> {
        tracing::info!("OCR engine with specific language (delegated to Python)");
        Ok(Self)
    }

    /// Preprocess image (pass-through - actual processing in Python)
    pub fn preprocess_image(&self, image_data: &[u8]) -> Result<Vec<u8>, Box<dyn Error>> {
        Ok(image_data.to_vec())
    }

    /// Recognize text from image
    /// Note: This is a placeholder - actual OCR is performed by Python gRPC server
    pub fn recognize_text(&self, _image_data: &[u8]) -> Result<OcrResult, Box<dyn Error>> {
        // Return placeholder indicating OCR is done via gRPC
        Ok(OcrResult {
            text: String::new(),
            confidence: 0.0,
            words: Vec::new(),
        })
    }

    /// Get supported languages
    pub fn get_supported_languages(&self) -> Result<Vec<String>, Box<dyn Error>> {
        // Return common languages supported by Windows OCR
        Ok(vec![
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
        ])
    }

    /// Check if a language is supported
    pub fn is_language_supported(language_tag: &str) -> Result<bool, Box<dyn Error>> {
        let supported = matches!(
            language_tag.to_lowercase().as_str(),
            "en-us" | "en-gb" | "de-de" | "fr-fr" | "es-es" | "it-it" |
            "ja-jp" | "ko-kr" | "zh-cn" | "zh-tw"
        );
        Ok(supported)
    }
}

impl Default for OcrEngine {
    fn default() -> Self {
        Self
    }
}

/// OCR recognition result
#[derive(Debug, Clone, Default)]
pub struct OcrResult {
    pub text: String,
    pub confidence: f32,
    pub words: Vec<OcrWord>,
}

/// Individual word with position information
#[derive(Debug, Clone, Default)]
pub struct OcrWord {
    pub text: String,
    pub confidence: f32,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}
