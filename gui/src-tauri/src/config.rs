use serde::{Deserialize, Serialize};

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

impl DaemonConfig {
    pub fn url(&self) -> String {
        format!("http://{}:{}", self.host, self.port)
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
