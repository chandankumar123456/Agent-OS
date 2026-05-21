//! Screen Capture Module
//!
//! Provides screen capture using GDI BitBlt (Windows) or Python gRPC fallback.
//! On Windows, this uses the `windows` crate for native GDI calls.
//! On non-Windows platforms, capture is delegated to the Python gRPC server.

use std::time::{Duration, Instant};
use thiserror::Error;

/// Errors that can occur during screen capture
#[derive(Error, Debug)]
pub enum CaptureError {
    #[error("Capture failed: {0}")]
    Generic(String),

    #[error("Failed to initialize capture: {0}")]
    InitializationError(String),

    #[error("No displays found")]
    NoDisplaysFound,

    #[error("Failed to acquire frame: {0}")]
    FrameAcquisitionError(String),

    #[error("Access denied - may need elevated privileges")]
    AccessDenied,

    #[error("Timeout waiting for frame")]
    Timeout,

    #[error("Invalid region: {0}")]
    InvalidRegion(String),

    #[error("Platform not supported for native capture")]
    UnsupportedPlatform,
}

/// Represents a captured frame
#[derive(Debug, Clone)]
pub struct CapturedFrame {
    /// Raw image data (BGRA format from GDI)
    pub data: Vec<u8>,
    /// Width in pixels
    pub width: u32,
    /// Height in pixels
    pub height: u32,
    /// Capture timestamp
    pub timestamp: Instant,
    /// Capture duration
    pub capture_time: Duration,
}

/// Rectangle region for partial capture
#[derive(Debug, Clone, Copy)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

/// Screen capture using GDI BitBlt (Windows native)
///
/// Uses the Windows GDI API to capture the screen. This is a well-established
/// approach that works on all Windows versions without needing DirectX.
/// Performance is typically 10-30ms for a full 1920x1080 capture.
#[cfg(target_os = "windows")]
pub struct GdiCapture;

#[cfg(target_os = "windows")]
impl GdiCapture {
    /// Capture the entire primary monitor using GDI BitBlt
    pub fn capture_full_screen() -> Result<CapturedFrame, CaptureError> {
        use windows::Win32::Graphics::Gdi::{
            BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject,
            GetDIBits, SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS,
            GetDC, ReleaseDC, SRCCOPY,
        };
        use windows::Win32::Foundation::RECT;
        use windows::Win32::UI::WindowsAndMessaging::{GetDesktopWindow, GetWindowRect};

        let start = Instant::now();

        unsafe {
            // Get desktop window and its DC
            let desktop_hwnd = GetDesktopWindow();
            let desktop_dc = GetDC(desktop_hwnd);
            if desktop_dc.is_invalid() {
                return Err(CaptureError::InitializationError(
                    "Failed to get desktop DC".to_string(),
                ));
            }

            // Get screen dimensions
            let mut rect: RECT = std::mem::zeroed();
            if GetWindowRect(desktop_hwnd, &mut rect).is_err() {
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::InitializationError(
                    "Failed to get desktop window rect".to_string(),
                ));
            }

            let width = (rect.right - rect.left) as u32;
            let height = (rect.bottom - rect.top) as u32;

            if width == 0 || height == 0 {
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::InitializationError(
                    "Invalid screen dimensions".to_string(),
                ));
            }

            // Create compatible DC and bitmap
            let mem_dc = CreateCompatibleDC(desktop_dc);
            if mem_dc.is_invalid() {
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::InitializationError(
                    "Failed to create compatible DC".to_string(),
                ));
            }

            let bitmap = CreateCompatibleBitmap(desktop_dc, width as i32, height as i32);
            if bitmap.is_invalid() {
                let _ = DeleteDC(mem_dc);
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::InitializationError(
                    "Failed to create compatible bitmap".to_string(),
                ));
            }

            // Select bitmap into memory DC
            let old_bitmap = SelectObject(mem_dc, bitmap);
            if old_bitmap.is_invalid() {
                let _ = DeleteObject(bitmap);
                let _ = DeleteDC(mem_dc);
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::InitializationError(
                    "Failed to select bitmap into DC".to_string(),
                ));
            }

            // BitBlt: copy screen content to memory DC
            if BitBlt(
                mem_dc,
                0,
                0,
                width as i32,
                height as i32,
                desktop_dc,
                0,
                0,
                SRCCOPY,
            ).is_err() {
                let _ = SelectObject(mem_dc, old_bitmap);
                let _ = DeleteObject(bitmap);
                let _ = DeleteDC(mem_dc);
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::FrameAcquisitionError(
                    "BitBlt failed".to_string(),
                ));
            }

            // Get bitmap info
            let mut bmp_info: BITMAPINFO = std::mem::zeroed();
            bmp_info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
            bmp_info.bmiHeader.biWidth = width as i32;
            bmp_info.bmiHeader.biHeight = -(height as i32); // Negative for top-down
            bmp_info.bmiHeader.biPlanes = 1;
            bmp_info.bmiHeader.biBitCount = 32;
            bmp_info.bmiHeader.biCompression = BI_RGB.0;

            // Allocate pixel buffer
            let row_size = width as usize * 4;
            let pixel_count = row_size * height as usize;
            let mut pixels: Vec<u8> = vec![0u8; pixel_count];

            // Get pixel data (BGRA format from GDI)
            let dib_result = GetDIBits(
                desktop_dc,
                bitmap,
                0,
                height as u32,
                Some(pixels.as_mut_ptr() as *mut _),
                &mut bmp_info,
                DIB_RGB_COLORS,
            );
            if dib_result == 0 {
                let _ = SelectObject(mem_dc, old_bitmap);
                let _ = DeleteObject(bitmap);
                let _ = DeleteDC(mem_dc);
                let _ = ReleaseDC(desktop_hwnd, desktop_dc);
                return Err(CaptureError::FrameAcquisitionError(
                    "GetDIBits failed".to_string(),
                ));
            }

            // Cleanup
            let _ = SelectObject(mem_dc, old_bitmap);
            let _ = DeleteObject(bitmap);
            let _ = DeleteDC(mem_dc);
            let _ = ReleaseDC(desktop_hwnd, desktop_dc);

            // Convert BGRA to RGBA
            let rgba_data: Vec<u8> = pixels
                .chunks_exact(4)
                .flat_map(|bgra| [bgra[2], bgra[1], bgra[0], bgra[3]])
                .collect();

            Ok(CapturedFrame {
                data: rgba_data,
                width,
                height,
                timestamp: Instant::now(),
                capture_time: start.elapsed(),
            })
        }
    }

    /// Capture a specific region of the screen
    pub fn capture_region(region: Rect) -> Result<CapturedFrame, CaptureError> {
        let full = Self::capture_full_screen()?;

        // Validate region
        if region.x < 0
            || region.y < 0
            || region.x + region.width as i32 > full.width as i32
            || region.y + region.height as i32 > full.height as i32
        {
            return Err(CaptureError::InvalidRegion(format!(
                "Region {:?} exceeds frame bounds {}x{}",
                region, full.width, full.height
            )));
        }

        let bpp = 4; // RGBA
        let mut region_data = vec![0u8; (region.width * region.height) as usize * bpp];

        for row in 0..region.height {
            let src_offset =
                ((region.y + row as i32) * full.width as i32 + region.x) as usize * bpp;
            let dst_offset = (row * region.width) as usize * bpp;
            let row_size = region.width as usize * bpp;

            region_data[dst_offset..dst_offset + row_size]
                .copy_from_slice(&full.data[src_offset..src_offset + row_size]);
        }

        Ok(CapturedFrame {
            data: region_data,
            width: region.width,
            height: region.height,
            timestamp: full.timestamp,
            capture_time: full.capture_time,
        })
    }
}

#[cfg(not(target_os = "windows"))]
pub struct GdiCapture;

#[cfg(not(target_os = "windows"))]
impl GdiCapture {
    pub fn capture_full_screen() -> Result<CapturedFrame, CaptureError> {
        Err(CaptureError::UnsupportedPlatform)
    }

    pub fn capture_region(_region: Rect) -> Result<CapturedFrame, CaptureError> {
        Err(CaptureError::UnsupportedPlatform)
    }
}

/// Capture a region of the screen, returning PNG-encoded bytes
pub fn capture_region(x: i32, y: i32, width: i32, height: i32) -> Result<Vec<u8>, CaptureError> {
    let frame = if width > 0 && height > 0 {
        GdiCapture::capture_region(Rect {
            x,
            y,
            width: width as u32,
            height: height as u32,
        })?
    } else {
        GdiCapture::capture_full_screen()?
    };

    // Encode to PNG
    let img = image::RgbaImage::from_raw(frame.width, frame.height, frame.data).ok_or(
        CaptureError::FrameAcquisitionError("Failed to create image from raw data".to_string()),
    )?;

    let mut png_data = std::io::Cursor::new(Vec::new());
    img.write_to(&mut png_data, image::ImageFormat::Png)
        .map_err(|e| {
            CaptureError::FrameAcquisitionError(format!("Failed to encode PNG: {}", e))
        })?;

    Ok(png_data.into_inner())
}

/// Utility functions for screen capture
pub mod utils {
    use super::*;
    use image::RgbaImage;

    /// Save a captured frame to a PNG file
    pub fn save_to_png(frame: &CapturedFrame, path: &str) -> Result<(), Box<dyn std::error::Error>> {
        let img: RgbaImage = RgbaImage::from_raw(frame.width, frame.height, frame.data.clone())
            .ok_or("Failed to create image buffer")?;
        img.save(path)?;
        Ok(())
    }

    /// Get the number of displays
    pub fn get_display_count() -> Result<u32, CaptureError> {
        #[cfg(target_os = "windows")]
        {
            use windows::Win32::UI::WindowsAndMessaging::{GetSystemMetrics, SM_CMONITORS};
            let count = unsafe { GetSystemMetrics(SM_CMONITORS) };
            if count > 0 {
                return Ok(count as u32);
            }
            Ok(1) // At least primary monitor
        }
        #[cfg(not(target_os = "windows"))]
        {
            Ok(1)
        }
    }

    /// Get primary display resolution
    pub fn get_display_resolution(_display_index: u32) -> Result<(u32, u32), CaptureError> {
        #[cfg(target_os = "windows")]
        {
            use windows::Win32::Graphics::Gdi::{GetDeviceCaps, HORZRES, VERTRES};
            use windows::Win32::Foundation::HWND;
            use windows::Win32::Graphics::Gdi::GetDC;
            unsafe {
                let dc = GetDC(HWND::default());
                let w = GetDeviceCaps(dc, HORZRES) as u32;
                let h = GetDeviceCaps(dc, VERTRES) as u32;
                Ok((w, h))
            }
        }
        #[cfg(not(target_os = "windows"))]
        {
            Ok((1920, 1080))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_region_validation() {
        let frame = CapturedFrame {
            data: vec![0u8; 100 * 100 * 4],
            width: 100,
            height: 100,
            timestamp: Instant::now(),
            capture_time: Duration::from_millis(1),
        };

        // Valid region
        let result = extract_region_test_helper(&frame, Rect { x: 0, y: 0, width: 50, height: 50 });
        assert!(result.is_ok());

        // Invalid region (exceeds bounds)
        let result = extract_region_test_helper(&frame, Rect { x: 50, y: 50, width: 100, height: 100 });
        assert!(result.is_err());
    }

    fn extract_region_test_helper(frame: &CapturedFrame, region: Rect) -> Result<CapturedFrame, CaptureError> {
        if region.x < 0
            || region.y < 0
            || region.x + region.width as i32 > frame.width as i32
            || region.y + region.height as i32 > frame.height as i32
        {
            return Err(CaptureError::InvalidRegion(format!(
                "Region {:?} exceeds frame bounds {}x{}",
                region, frame.width, frame.height
            )));
        }

        let bpp = 4;
        let mut region_data = vec![0u8; (region.width * region.height) as usize * bpp];

        for row in 0..region.height {
            let src_offset = ((region.y + row as i32) * frame.width as i32 + region.x) as usize * bpp;
            let dst_offset = (row * region.width) as usize * bpp;
            let row_size = region.width as usize * bpp;
            region_data[dst_offset..dst_offset + row_size]
                .copy_from_slice(&frame.data[src_offset..src_offset + row_size]);
        }

        Ok(CapturedFrame {
            data: region_data,
            width: region.width,
            height: region.height,
            timestamp: frame.timestamp,
            capture_time: frame.capture_time,
        })
    }
}
