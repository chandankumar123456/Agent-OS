use std::path::PathBuf;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)]
pub struct Config {
    pub supervisor_host: String,
    pub supervisor_port: u16,
    pub refresh_interval_ms: u64,
    pub max_log_lines: usize,
    pub max_tasks_displayed: usize,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            supervisor_host: "127.0.0.1".to_string(),
            supervisor_port: 8080,
            refresh_interval_ms: 1000,
            max_log_lines: 1000,
            max_tasks_displayed: 100,
        }
    }
}

#[allow(dead_code)]
impl Config {
    pub fn supervisor_url(&self) -> String {
        format!("http://{}:{}", self.supervisor_host, self.supervisor_port)
    }

    pub fn websocket_url(&self) -> String {
        format!("ws://{}:{}/ws", self.supervisor_host, self.supervisor_port)
    }
}

#[allow(dead_code)]
pub fn default_config_path() -> Option<PathBuf> {
    dirs::config_dir().map(|d| d.join("agentos/tui.toml"))
}
