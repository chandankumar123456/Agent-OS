pub mod bridge;
pub mod capture;
pub mod ocr;
pub mod automation;

// Re-export protocol types from desktop-protocol crate
pub use desktop_protocol;

// Re-export capture types
pub use capture::{DxgiCapture, GdiCapture, CapturedFrame, Rect, CaptureError};
