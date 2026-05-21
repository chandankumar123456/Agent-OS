use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use anyhow::{Result, Context};

pub const DEFAULT_SUPERVISOR_HOST: &str = "127.0.0.1";
pub const DEFAULT_SUPERVISOR_PORT: u16 = 8080;
pub const DEFAULT_LOG_LEVEL: &str = "info";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    /// Supervisor connection settings
    pub supervisor: SupervisorConfig,
    
    /// Data directory
    pub data_dir: PathBuf,
    
    /// Log level
    pub log_level: String,
    
    /// Auto-start daemon if not running
    pub auto_start_daemon: bool,
    
    /// Default task timeout in seconds (0 = no timeout)
    pub default_timeout: u64,
    
    /// Output format preference
    pub default_output_format: OutputFormat,
    
    /// Desktop automation settings
    pub desktop: DesktopConfig,
    
    /// Additional settings
    #[serde(flatten)]
    pub extra: HashMap<String, toml::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupervisorConfig {
    pub host: String,
    pub port: u16,
    pub api_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopConfig {
    /// Delay before screenshots in ms
    pub screenshot_delay_ms: u64,
    
    /// Default click interval in ms
    pub click_interval_ms: u64,
    
    /// OCR confidence threshold (0.0 - 1.0)
    pub ocr_confidence_threshold: f64,
    
    /// Window matching strategy (exact, contains, fuzzy)
    pub window_match_strategy: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OutputFormat {
    Text,
    Json,
}

impl Config {
    /// Load configuration from default locations
    pub fn load_default() -> Result<Self> {
        // Try config file locations in order of priority
        let config_paths = vec![
            dirs::config_dir().map(|d| d.join("agentos/config.toml")),
            Some(PathBuf::from("./agentos.toml")),
            Some(PathBuf::from("~/.agentos/config.toml")),
        ];

        for path in config_paths.into_iter().flatten() {
            if path.exists() {
                return Self::from_file(&path);
            }
        }

        // Return default config if no file found
        Ok(Self::default())
    }

    /// Load configuration from specific file
    pub fn from_file(path: &PathBuf) -> Result<Self> {
        let content = std::fs::read_to_string(path)
            .with_context(|| format!("Failed to read config file: {:?}", path))?;
        
        let config: Config = toml::from_str(&content)
            .with_context(|| format!("Failed to parse config file: {:?}", path))?;
        
        Ok(config)
    }

    /// Save configuration to file
    pub fn save_to_file(&self, path: &PathBuf) -> Result<()> {
        let content = toml::to_string_pretty(self)
            .context("Failed to serialize config")?;
        
        std::fs::write(path, content)
            .with_context(|| format!("Failed to write config file: {:?}", path))?;
        
        Ok(())
    }

    /// Get supervisor API base URL (legacy, kept for compatibility)
    #[allow(dead_code)]
    pub fn supervisor_url(&self) -> String {
        format!("http://{}:{}", self.supervisor.host, self.supervisor.port)
    }

    /// Set a configuration value
    pub fn set(&mut self, key: &str, value: &str) -> Result<()> {
        match key {
            "supervisor.host" => self.supervisor.host = value.to_string(),
            "supervisor.port" => {
                self.supervisor.port = value.parse()
                    .context("Invalid port number")?;
            }
            "data_dir" => self.data_dir = PathBuf::from(value),
            "log_level" => self.log_level = value.to_string(),
            "auto_start_daemon" => {
                self.auto_start_daemon = value.parse()
                    .context("Invalid boolean value")?;
            }
            "default_timeout" => {
                self.default_timeout = value.parse()
                    .context("Invalid timeout value")?;
            }
            "default_output_format" => {
                self.default_output_format = match value {
                    "text" => OutputFormat::Text,
                    "json" => OutputFormat::Json,
                    _ => anyhow::bail!("Invalid output format: {}", value),
                };
            }
            "desktop.screenshot_delay_ms" => {
                self.desktop.screenshot_delay_ms = value.parse()
                    .context("Invalid delay value")?;
            }
            "desktop.click_interval_ms" => {
                self.desktop.click_interval_ms = value.parse()
                    .context("Invalid interval value")?;
            }
            "desktop.ocr_confidence_threshold" => {
                self.desktop.ocr_confidence_threshold = value.parse()
                    .context("Invalid confidence value")?;
            }
            "desktop.window_match_strategy" => {
                self.desktop.window_match_strategy = value.to_string();
            }
            _ => anyhow::bail!("Unknown configuration key: {}", key),
        }
        
        Ok(())
    }

    /// Get a configuration value
    pub fn get(&self, key: &str) -> Option<String> {
        match key {
            "supervisor.host" => Some(self.supervisor.host.clone()),
            "supervisor.port" => Some(self.supervisor.port.to_string()),
            "data_dir" => Some(self.data_dir.to_string_lossy().to_string()),
            "log_level" => Some(self.log_level.clone()),
            "auto_start_daemon" => Some(self.auto_start_daemon.to_string()),
            "default_timeout" => Some(self.default_timeout.to_string()),
            "default_output_format" => Some(format!("{:?}", self.default_output_format).to_lowercase()),
            "desktop.screenshot_delay_ms" => Some(self.desktop.screenshot_delay_ms.to_string()),
            "desktop.click_interval_ms" => Some(self.desktop.click_interval_ms.to_string()),
            "desktop.ocr_confidence_threshold" => Some(self.desktop.ocr_confidence_threshold.to_string()),
            "desktop.window_match_strategy" => Some(self.desktop.window_match_strategy.clone()),
            _ => None,
        }
    }
}

impl Default for Config {
    fn default() -> Self {
        Self {
            supervisor: SupervisorConfig {
                host: DEFAULT_SUPERVISOR_HOST.to_string(),
                port: DEFAULT_SUPERVISOR_PORT,
                api_version: "v1".to_string(),
            },
            data_dir: dirs::data_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join("agentos"),
            log_level: DEFAULT_LOG_LEVEL.to_string(),
            auto_start_daemon: true,
            default_timeout: 300,
            default_output_format: OutputFormat::Text,
            desktop: DesktopConfig {
                screenshot_delay_ms: 500,
                click_interval_ms: 10,
                ocr_confidence_threshold: 0.7,
                window_match_strategy: "contains".to_string(),
            },
            extra: HashMap::new(),
        }
    }
}

/// Get default config file path
pub fn default_config_path() -> Result<PathBuf> {
    let config_dir = dirs::config_dir()
        .context("Could not determine config directory")?;
    
    Ok(config_dir.join("agentos/config.toml"))
}

/// Initialize default configuration
pub fn init_default_config(force: bool) -> Result<PathBuf> {
    let config_path = default_config_path()?;
    
    if config_path.exists() && !force {
        anyhow::bail!("Configuration file already exists at {:?}. Use --force to overwrite.", config_path);
    }
    
    // Create parent directory if it doesn't exist
    if let Some(parent) = config_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    
    let config = Config::default();
    config.save_to_file(&config_path)?;
    
    Ok(config_path)
}
