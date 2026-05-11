pub mod bridge;
pub mod capture;
pub mod ocr;
pub mod automation;
pub mod server;

// Re-export protocol types from desktop-protocol crate
pub use desktop_protocol;

// Re-export capture types
pub use capture::{GdiCapture, CapturedFrame, Rect, CaptureError};

// Re-export server
pub use server::DesktopAutomationService;
