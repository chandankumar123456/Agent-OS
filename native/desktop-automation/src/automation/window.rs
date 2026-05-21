//! Window automation module
//! Platform-specific window management using native APIs.
//! On Windows, uses Win32 APIs for window enumeration, click, and text input.
//! On non-Windows platforms, provides stub implementations.

#[cfg(target_os = "windows")]
mod platform {
    use std::mem::size_of;
    use windows::Win32::Foundation::{BOOL, HWND, LPARAM, POINT, RECT, TRUE};
    use windows::Win32::Graphics::Gdi::ClientToScreen;
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, INPUT_MOUSE, KEYBDINPUT, KEYBD_EVENT_FLAGS,
        KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
        MOUSEINPUT, VIRTUAL_KEY,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        EnumWindows, GetWindowRect, GetWindowTextW, IsWindowVisible, SetCursorPos,
        SetForegroundWindow, ShowWindow, SW_RESTORE,
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
                let _ = EnumWindows(
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

        /// Get window position and size in screen coordinates
        pub fn get_position(&self) -> (i32, i32, u32, u32) {
            unsafe {
                let mut rect = RECT::default();
                if GetWindowRect(self.hwnd, &mut rect).is_ok() {
                    let left = rect.left;
                    let top = rect.top;
                    let width = (rect.right - rect.left) as u32;
                    let height = (rect.bottom - rect.top) as u32;
                    return (left, top, width, height);
                }
            }

            (0, 0, 0, 0)
        }

        /// Bring window to foreground and restore if minimized
        pub fn bring_to_front(&self) -> bool {
            unsafe {
                // Restore window if minimized
                let _ = ShowWindow(self.hwnd, SW_RESTORE);
                // Bring to foreground
                SetForegroundWindow(self.hwnd).as_bool()
            }
        }

        /// Check if window is valid and visible
        pub fn is_valid(&self) -> bool {
            unsafe { IsWindowVisible(self.hwnd).as_bool() }
        }

        /// Perform a mouse click at the specified client coordinates
        pub fn click(&self, x: i32, y: i32) -> bool {
            unsafe {
                // Bring window to front first
                self.bring_to_front();

                // Convert client coordinates to screen coordinates
                let mut point = POINT { x, y };
                if !ClientToScreen(self.hwnd, &mut point).as_bool() {
                    return false;
                }

                // Move cursor to position
                if SetCursorPos(point.x, point.y).is_err() {
                    return false;
                }

                // Create mouse down input
                let down_input = INPUT {
                    r#type: INPUT_MOUSE,
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

                // Create mouse up input
                let up_input = INPUT {
                    r#type: INPUT_MOUSE,
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

                // Send mouse events
                let inputs = [down_input, up_input];
                let sent = SendInput(&inputs, size_of::<INPUT>() as i32);

                sent as usize == inputs.len()
            }
        }

        /// Type text using SendInput with KEYEVENTF_UNICODE
        pub fn type_text(&self, text: &str) -> bool {
            unsafe {
                // Bring window to front first
                self.bring_to_front();

                // Build input array for each character
                let mut inputs: Vec<INPUT> = Vec::with_capacity(text.len() * 2);

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
                                dwFlags: KEYBD_EVENT_FLAGS(
                                    KEYEVENTF_UNICODE.0 | KEYEVENTF_KEYUP.0,
                                ),
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

        /// Press a special key (Enter, Tab, etc.)
        pub fn press_key(&self, vk_code: u16) -> bool {
            unsafe {
                self.bring_to_front();

                // Key down
                let down_input = INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wVk: VIRTUAL_KEY(vk_code),
                            wScan: 0,
                            dwFlags: KEYBD_EVENT_FLAGS(0),
                            time: 0,
                            dwExtraInfo: 0,
                        },
                    },
                };

                // Key up
                let up_input = INPUT {
                    r#type: INPUT_KEYBOARD,
                    Anonymous: INPUT_0 {
                        ki: KEYBDINPUT {
                            wVk: VIRTUAL_KEY(vk_code),
                            wScan: 0,
                            dwFlags: KEYEVENTF_KEYUP,
                            time: 0,
                            dwExtraInfo: 0,
                        },
                    },
                };

                let inputs = [down_input, up_input];
                let sent = SendInput(&inputs, size_of::<INPUT>() as i32);
                sent as usize == inputs.len()
            }
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
            let _ = EnumWindows(
                Some(enum_window_callback),
                LPARAM(&mut windows as *mut _ as isize),
            );
        }

        windows
    }
}

#[cfg(target_os = "windows")]
pub use platform::*;

// Stub implementation for non-Windows platforms
#[cfg(not(target_os = "windows"))]
pub struct WindowAutomation;

#[cfg(not(target_os = "windows"))]
impl WindowAutomation {
    pub fn find_by_title(_title: &str, _partial_match: bool) -> Option<()> {
        None
    }
}

#[cfg(not(target_os = "windows"))]
pub fn enumerate_windows() -> Vec<(isize, String)> {
    Vec::new()
}
