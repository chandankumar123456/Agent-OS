use std::path::PathBuf;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)]
pub struct Config {
    pub refresh_interval_ms: u64,
    pub max_log_lines: usize,
    pub max_tasks_displayed: usize,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            refresh_interval_ms: 1000,
            max_log_lines: 1000,
            max_tasks_displayed: 100,
        }
    }
}

#[allow(dead_code)]
pub fn default_config_path() -> Option<PathBuf> {
    dirs::config_dir().map(|d| d.join("agentos/tui.toml"))
}
