pub mod bridge;
pub mod capture;
pub mod ocr;
pub mod automation;
pub mod server;

// Re-export protocol types from ipc-protocol crate
pub use agentos_ipc_protocol::desktop as desktop_protocol;

// Re-export capture types
pub use capture::{CapturedFrame, CaptureError, GdiCapture, Rect};

// Re-export server
pub use server::DesktopAutomationService;
