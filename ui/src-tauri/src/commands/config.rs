use tauri::command;
use serde::{Deserialize, Serialize};
use crate::config::AppConfig;

#[derive(Debug, Serialize, Deserialize)]
pub struct ConfigUpdate {
    pub auto_start_daemon: Option<bool>,
    pub start_minimized: Option<bool>,
    pub notifications_enabled: Option<bool>,
    pub global_shortcuts_enabled: Option<bool>,
    pub daemon_host: Option<String>,
    pub daemon_port: Option<u16>,
}

#[command]
pub fn get_config() -> Result<AppConfig, String> {
    Ok(AppConfig::load())
}

#[command]
pub fn set_config(update: ConfigUpdate) -> Result<AppConfig, String> {
    let mut config = AppConfig::load();

    if let Some(val) = update.auto_start_daemon {
        config.auto_start_daemon = val;
    }
    if let Some(val) = update.start_minimized {
        config.start_minimized = val;
    }
    if let Some(val) = update.notifications_enabled {
        config.notifications_enabled = val;
    }
    if let Some(val) = update.global_shortcuts_enabled {
        config.global_shortcuts_enabled = val;
    }
    if let Some(host) = update.daemon_host {
        config.daemon.host = host;
    }
    if let Some(port) = update.daemon_port {
        config.daemon.port = port;
    }

    config.save()?;
    Ok(config)
}
