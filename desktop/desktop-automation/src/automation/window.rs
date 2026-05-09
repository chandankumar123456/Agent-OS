use windows::Win32::Foundation::{BOOL, HWND, LPARAM, POINT, RECT, TRUE};
use windows::Win32::Graphics::Gdi::ClientToScreen;
use windows::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClientRect, GetWindowTextW, IsWindowVisible, SetCursorPos,
};

/// Window enumeration callback function
unsafe extern "system" fn enum_window_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let windows_ref = &mut *(lparam.0 as *mut Vec<(HWND, String)>);
    
    // Skip invisible windows
    if !IsWindowVisible(hwnd).as_bool() {
        return TRUE;
    }
    
    // Get window title
    let mut title = [0u16; 512];
    let len = GetWindowTextW(hwnd, &mut title);
    
    if len > 0 {
        let title_str = String::from_utf16_lossy(&title[..len as usize]);
        windows_ref.push((hwnd, title_str));
    }
    
    TRUE
}

pub struct WindowAutomation {
    hwnd: HWND,
}

impl WindowAutomation {
    pub fn new(hwnd: HWND) -> Self {
        Self { hwnd }
    }
    
    pub fn find_by_title(title: &str, partial_match: bool) -> Option<HWND> {
        let mut windows: Vec<(HWND, String)> = Vec::new();
        
        unsafe {
            EnumWindows(
                Some(enum_window_callback),
                LPARAM(&mut windows as *mut _ as isize),
            );
        }
        
        for (hwnd, win_title) in windows.iter() {
            let matches = if partial_match {
                win_title.to_lowercase().contains(&title.to_lowercase())
            } else {
                win_title == title
            };
            
            if matches {
                return Some(*hwnd);
            }
        }
        
        None
    }
    
    pub fn get_position(&self) -> (i32, i32, u32, u32) {
        unsafe {
            let mut rect = RECT::default();
            if GetClientRect(self.hwnd, &mut rect).is_ok() {
                let left = rect.left;
                let top = rect.top;
                let width = (rect.right - rect.left) as u32;
                let height = (rect.bottom - rect.top) as u32;
                return (left, top, width, height);
            }
        }
        
        (0, 0, 0, 0)
    }
    
    pub fn click(&self, x: i32, y: i32) -> bool {
        unsafe {
            // Convert client coordinates to screen coordinates
            let mut point = POINT { x, y };
            ClientToScreen(self.hwnd, &mut point);
            
            // Move cursor
            SetCursorPos(point.x, point.y);
            
            // TODO: Implement mouse click using SendInput
            // For now, just move cursor
            
            true
        }
    }
    
    pub fn type_text(&self, _text: &str) -> bool {
        // For now, return true (actual text input requires more complex implementation)
        // This would typically use SendInput or WM_CHAR messages
        true
    }
    
    pub fn get_title(&self) -> String {
        unsafe {
            let mut title = [0u16; 512];
            let len = GetWindowTextW(self.hwnd, &mut title);
            
            if len > 0 {
                String::from_utf16_lossy(&title[..len as usize])
            } else {
                String::new()
            }
        }
    }
}

pub fn enumerate_windows() -> Vec<(HWND, String)> {
    let mut windows = Vec::new();
    
    unsafe {
        EnumWindows(
            Some(enum_window_callback),
            LPARAM(&mut windows as *mut _ as isize),
        );
    }
    
    windows
}
