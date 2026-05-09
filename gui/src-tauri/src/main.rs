#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use tauri::{generate_context, generate_handler, Manager, RunEvent};

mod commands;
mod config;
mod notifications;
mod shortcuts;
mod tray;

fn main() {
    let system_tray = tray::create_system_tray();

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // Focus existing window when second instance starts
            if let Some(window) = app.get_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .system_tray(system_tray)
        .on_system_tray_event(tray::handle_system_tray_event)
        .setup(|app| {
            // Register global shortcuts
            if let Err(e) = shortcuts::register_global_shortcuts(app.handle()) {
                eprintln!("Failed to register global shortcuts: {}", e);
            }

            // Check if should start minimized
            let config = config::AppConfig::default();
            if config.start_minimized {
                if let Some(window) = app.get_window("main") {
                    let _ = window.hide();
                }
            }

            Ok(())
        })
        .invoke_handler(generate_handler![
            commands::get_daemon_status,
            commands::start_daemon,
            commands::stop_daemon,
            commands::get_config,
            commands::set_config,
            commands::show_notification,
            commands::get_app_version,
        ])
        .on_window_event(|event| match event.event() {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                // Hide instead of close when clicking X
                event.window().hide().unwrap();
                api.prevent_close();
            }
            _ => {}
        })
        .build(generate_context!())
        .expect("error while running tauri application")
        .run(|_app_handle, event| match event {
            RunEvent::ExitRequested { api, .. } => {
                api.prevent_exit();
            }
            RunEvent::Exit => {
                // Cleanup global shortcuts on exit
                let _ = shortcuts::unregister_global_shortcuts(_app_handle);
            }
            _ => {}
        });
}
