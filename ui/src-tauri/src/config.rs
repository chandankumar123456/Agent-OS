use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize)]
pub struct DaemonConfig {
    pub host: String,
    pub port: u16,
}

impl Default for DaemonConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 8080,
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AppConfig {
    pub daemon: DaemonConfig,
    pub auto_start_daemon: bool,
    pub start_minimized: bool,
    pub notifications_enabled: bool,
    pub global_shortcuts_enabled: bool,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            daemon: DaemonConfig::default(),
            auto_start_daemon: true,
            start_minimized: false,
            notifications_enabled: true,
            global_shortcuts_enabled: true,
        }
    }
}

impl AppConfig {
    /// Load config from disk, or return default if not found
    pub fn load() -> Self {
        let path = Self::config_path();
        if path.exists() {
            match fs::read_to_string(&path) {
                Ok(content) => match toml::from_str(&content) {
                    Ok(config) => return config,
                    Err(e) => eprintln!("Failed to parse config file: {}", e),
                },
                Err(e) => eprintln!("Failed to read config file: {}", e),
            }
        }
        Self::default()
    }

    /// Save config to disk
    pub fn save(&self) -> Result<(), String> {
        let path = Self::config_path();
        if let Some(parent) = path.parent() {
            if let Err(e) = fs::create_dir_all(parent) {
                return Err(format!("Failed to create config directory: {}", e));
            }
        }
        let content = match toml::to_string_pretty(self) {
            Ok(c) => c,
            Err(e) => return Err(format!("Failed to serialize config: {}", e)),
        };
        match fs::write(&path, content) {
            Ok(_) => Ok(()),
            Err(e) => Err(format!("Failed to write config file: {}", e)),
        }
    }

    /// Get the config file path
    pub fn config_path() -> PathBuf {
        let config_dir = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
        config_dir.join("AgentOS").join("config.toml")
    }
}
