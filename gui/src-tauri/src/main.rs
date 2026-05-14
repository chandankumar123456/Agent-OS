#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use tauri::{generate_context, generate_handler, Manager, RunEvent};
use crate::commands::daemon::cleanup_daemon;

mod commands;
mod config;
mod events;
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
            if let Err(e) = shortcuts::register_global_shortcuts(&app.handle()) {
                eprintln!("Failed to register global shortcuts: {}", e);
            }

            // Load persisted config and apply settings
            let config = config::AppConfig::load();
            if config.start_minimized {
                if let Some(window) = app.get_window("main") {
                    let _ = window.hide();
                }
            }

            // Start WebSocket event bridge to Supervisor
            events::start_event_bridge(app.handle());

            Ok(())
        })
        .invoke_handler(generate_handler![
            commands::daemon::get_daemon_status,
            commands::daemon::start_daemon,
            commands::daemon::stop_daemon,
            commands::daemon::restart_daemon,
            commands::daemon::check_daemon_installation,
            commands::config::get_config,
            commands::config::set_config,
            commands::notifications::show_notification,
            commands::system::get_app_version,
            commands::keychain::get_secret,
            commands::keychain::set_secret,
            commands::keychain::delete_secret,
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
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { api, .. } => {
                api.prevent_exit();
            }
            RunEvent::Exit => {
                // Cleanup global shortcuts on exit
                let _ = shortcuts::unregister_global_shortcuts(app_handle);
                
                // Cleanup daemon process on exit
                let rt = tokio::runtime::Handle::current();
                rt.block_on(async {
                    if let Err(e) = cleanup_daemon().await {
                        log::error!("Failed to cleanup daemon on exit: {}", e);
                    }
                });
            }
            _ => {}
        });
}
