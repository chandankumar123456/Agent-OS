use tauri::{AppHandle, GlobalShortcutManager, Manager};

pub fn register_global_shortcuts(app: &AppHandle) -> Result<(), String> {
    let app_handle = app.clone();
    
    // Register Ctrl+Shift+A to show AgentOS window
    if let Err(e) = app.global_shortcut_manager().register("Ctrl+Shift+A", move || {
        if let Some(window) = app_handle.get_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }) {
        eprintln!("Failed to register Ctrl+Shift+A: {}", e);
    }
    
    let _app_handle = app.clone();
    
    // Register Ctrl+Shift+S for screenshot
    if let Err(e) = app.global_shortcut_manager().register("Ctrl+Shift+S", move || {
        // TODO: Trigger screenshot command
        println!("Screenshot hotkey pressed");
    }) {
        eprintln!("Failed to register Ctrl+Shift+S: {}", e);
    }
    
    let app_handle = app.clone();
    
    // Register Ctrl+Shift+Q for quick task creation
    if let Err(e) = app.global_shortcut_manager().register("Ctrl+Shift+Q", move || {
        if let Some(window) = app_handle.get_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
            // Emit event to frontend to focus task input
            let _ = window.emit("focus-task-input", ());
        }
    }) {
        eprintln!("Failed to register Ctrl+Shift+Q: {}", e);
    }
    
    Ok(())
}

pub fn unregister_global_shortcuts(app: &AppHandle) -> Result<(), String> {
    let mut manager = app.global_shortcut_manager();
    manager.unregister_all().map_err(|e| e.to_string())?;
    Ok(())
}
