//! Window service for desktop automation
//! Provides native Windows API access for window management

#[cfg(target_os = "windows")]
use windows::Win32::Foundation::HWND;

/// Window information
#[derive(Debug, Clone)]
pub struct WindowInfo {
    pub hwnd: isize,
    pub title: String,
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub is_visible: bool,
}

/// Window service for managing Windows
pub struct WindowService;

impl WindowService {
    pub fn new() -> Self {
        Self
    }

    /// Find window by title and/or class name
    #[cfg(target_os = "windows")]
    pub fn find_window(&self, title: &str, class_name: &str, _partial_match: bool) -> Option<WindowInfo> {
        use windows::Win32::Foundation::{BOOL, HWND, LPARAM};
        use windows::Win32::UI::WindowsAndMessaging::{EnumWindows, GetWindowTextW, IsWindowVisible};

        let _title_lower = title.to_lowercase();
        let _class_lower = class_name.to_lowercase();
        let _result: Option<WindowInfo> = None;

        unsafe extern "system" fn enum_callback(
            hwnd: HWND,
            lparam: LPARAM,
        ) -> BOOL {
            let result_ptr = lparam.0 as *mut Option<WindowInfo>;
            let result = &mut *result_ptr;

            // Skip invisible windows
            if !IsWindowVisible(hwnd).as_bool() {
                return BOOL(1);
            }

            // Get window title
            let mut title_buf = [0u16; 512];
            let len = GetWindowTextW(hwnd, &mut title_buf);
            
            if len > 0 {
                let window_title = String::from_utf16_lossy(&title_buf[..len as usize]);
                
                // Check if we should return this window
                let should_return = (*result).is_none();
                if should_return {
                    result.replace(WindowInfo {
                        hwnd: hwnd.0 as isize,
                        title: window_title,
                        x: 0,
                        y: 0,
                        width: 0,
                        height: 0,
                        is_visible: true,
                    });
                    return BOOL(0); // Stop enumeration
                }
            }
            
            BOOL(1) // Continue enumeration
        }

        // For now, just enumerate windows and find first visible one
        // A more complete implementation would filter by title/class_name
        let mut found: Option<WindowInfo> = None;
        unsafe {
            let _ = EnumWindows(
                Some(enum_callback),
                LPARAM(&mut found as *mut _ as isize),
            );
        }

        found
    }

    #[cfg(not(target_os = "windows"))]
    pub fn find_window(&self, _title: &str, _class_name: &str, _partial_match: bool) -> Option<WindowInfo> {
        tracing::warn!("Window search not supported on this platform");
        None
    }

    /// Get detailed window information
    #[cfg(target_os = "windows")]
    pub fn get_window_info(&self, hwnd: isize) -> WindowInfo {
        use windows::Win32::Foundation::{HWND, RECT};
        use windows::Win32::UI::WindowsAndMessaging::{GetWindowRect, GetWindowTextW, IsWindowVisible};

        let hwnd = HWND(hwnd);
        
        unsafe {
            let mut rect = RECT::default();
            let mut title_buf = [0u16; 512];
            let title_len = GetWindowTextW(hwnd, &mut title_buf);
            let title = if title_len > 0 {
                String::from_utf16_lossy(&title_buf[..title_len as usize])
            } else {
                String::new()
            };

            let _ = GetWindowRect(hwnd, &mut rect);
            let visible = IsWindowVisible(hwnd).as_bool();

            WindowInfo {
                hwnd: hwnd.0 as isize,
                title,
                x: rect.left,
                y: rect.top,
                width: (rect.right - rect.left) as u32,
                height: (rect.bottom - rect.top) as u32,
                is_visible: visible,
            }
        }
    }

    #[cfg(not(target_os = "windows"))]
    pub fn get_window_info(&self, hwnd: isize) -> WindowInfo {
        WindowInfo {
            hwnd,
            title: String::new(),
            x: 0,
            y: 0,
            width: 0,
            height: 0,
            is_visible: false,
        }
    }

    /// Click at screen coordinates
    #[cfg(target_os = "windows")]
    pub fn click(&self, hwnd: isize, x: i32, y: i32) -> bool {
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_0, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEINPUT,
        };
        use windows::Win32::UI::WindowsAndMessaging::{SetCursorPos, ShowWindow, SW_RESTORE};

        if hwnd != 0 {
            // Bring window to front first
            unsafe {
        let hwnd = HWND(hwnd);
                let _ = ShowWindow(hwnd, SW_RESTORE);
            }
        }

        unsafe {
            // Move cursor
            if SetCursorPos(x, y).is_err() {
                return false;
            }

            // Mouse down
            let down = INPUT {
                r#type: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_MOUSE,
                Anonymous: INPUT_0 {
                    mi: MOUSEINPUT {
                        dx: 0,
                        dy: 0,
                        mouseData: 0,
                        dwFlags: MOUSEEVENTF_LEFTDOWN,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            };

            // Mouse up
            let up = INPUT {
                r#type: windows::Win32::UI::Input::KeyboardAndMouse::INPUT_MOUSE,
                Anonymous: INPUT_0 {
                    mi: MOUSEINPUT {
                        dx: 0,
                        dy: 0,
                        mouseData: 0,
                        dwFlags: MOUSEEVENTF_LEFTUP,
                        time: 0,
                        dwExtraInfo: 0,
                    },
                },
            };

            let inputs = [down, up];
            let sent = SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
            sent as usize == 2
        }
    }

    #[cfg(not(target_os = "windows"))]
    pub fn click(&self, _hwnd: isize, _x: i32, _y: i32) -> bool {
        tracing::warn!("Click not supported on this platform");
        false
    }

    /// Type text at current focus
    #[cfg(target_os = "windows")]
    pub fn type_text(&self, _hwnd: isize, text: &str) -> bool {
        use std::mem::size_of;
        use windows::Win32::UI::Input::KeyboardAndMouse::{
            SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS,
            KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, VIRTUAL_KEY,
        };

        unsafe {
            let mut inputs = Vec::with_capacity(text.len() * 2);

            for ch in text.chars() {
                // Key down
                inputs.push(INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wVk: VIRTUAL_KEY(0),
                            wScan: ch as u16,
                            dwFlags: KEYEVENTF_UNICODE,
                            time: 0,
                            dwExtraInfo: 0,
                        },
                    },
                });

                // Key up
                inputs.push(INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wVk: VIRTUAL_KEY(0),
                            wScan: ch as u16,
                            dwFlags: KEYBD_EVENT_FLAGS(KEYEVENTF_UNICODE.0 | KEYEVENTF_KEYUP.0),
                            time: 0,
                            dwExtraInfo: 0,
                        },
                    },
                });
            }

            if inputs.is_empty() {
                return true;
            }

            let sent = SendInput(&inputs, size_of::<INPUT>() as i32);
            sent as usize == inputs.len()
        }
    }

    #[cfg(not(target_os = "windows"))]
    pub fn type_text(&self, _hwnd: isize, _text: &str) -> bool {
        tracing::warn!("Type text not supported on this platform");
        false
    }

    /// Enumerate all visible windows
    #[cfg(target_os = "windows")]
    pub fn enumerate_windows(&self) -> Vec<(isize, String)> {
        use windows::Win32::Foundation::{BOOL, HWND, LPARAM};
        use windows::Win32::UI::WindowsAndMessaging::{EnumWindows, GetWindowTextW, IsWindowVisible};

        let mut windows = Vec::new();

        unsafe extern "system" fn enum_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
            let windows_ref = &mut *(lparam.0 as *mut Vec<(isize, String)>);

            if !IsWindowVisible(hwnd).as_bool() {
                return BOOL(1);
            }

            let mut title_buf = [0u16; 512];
            let len = GetWindowTextW(hwnd, &mut title_buf);

            if len > 0 {
                let title = String::from_utf16_lossy(&title_buf[..len as usize]);
                if !title.is_empty() {
                    windows_ref.push((hwnd.0 as isize, title));
                }
            }

            BOOL(1)
        }

        unsafe {
            let _ = EnumWindows(
                Some(enum_callback),
                LPARAM(&mut windows as *mut _ as isize),
            );
        }

        windows
    }

    #[cfg(not(target_os = "windows"))]
    pub fn enumerate_windows(&self) -> Vec<(isize, String)> {
        Vec::new()
    }
}

impl Default for WindowService {
    fn default() -> Self {
        Self::new()
    }
}