use crate::config::{Config, init_default_config, default_config_path};
use anyhow::{Result, Context};
use colored::*;
use comfy_table::Table;

pub fn set(config: &Config, key: String, value: String) -> Result<()> {
    let mut new_config = config.clone();
    
    new_config.set(&key, &value)
        .with_context(|| format!("Failed to set '{}' to '{}'", key, value))?;
    
    // Save to file
    let config_path = default_config_path()?;
    new_config.save_to_file(&config_path)?;
    
    println!("{} Set {} = {}", "✓".green(), key.cyan(), value);
    println!("  Saved to {:?}", config_path);
    
    Ok(())
}

pub fn get(config: &Config, key: String) -> Result<()> {
    match config.get(&key) {
        Some(value) => {
            println!("{} {} = {}", "●".blue(), key.cyan(), value);
        }
        None => {
            println!("{} Configuration key '{}' not found", "✗".red(), key);
            println!("  Available keys:");
            println!("    - supervisor.host");
            println!("    - supervisor.port");
            println!("    - data_dir");
            println!("    - log_level");
            println!("    - auto_start_daemon");
            println!("    - default_timeout");
            println!("    - default_output_format");
            println!("    - desktop.screenshot_delay_ms");
            println!("    - desktop.click_interval_ms");
            println!("    - desktop.ocr_confidence_threshold");
            println!("    - desktop.window_match_strategy");
        }
    }
    
    Ok(())
}

pub fn list(config: &Config) -> Result<()> {
    println!("{}", "Current Configuration".bold().underline());
    println!();
    
    let mut table = Table::new();
    table.set_header(vec!["Key".bold(), "Value".bold()]);
    
    table.add_row(vec!["supervisor.host", &config.supervisor.host]);
    table.add_row(vec!["supervisor.port", &config.supervisor.port.to_string()]);
    table.add_row(vec!["data_dir", &config.data_dir.to_string_lossy()]);
    table.add_row(vec!["log_level", &config.log_level]);
    table.add_row(vec!["auto_start_daemon", &config.auto_start_daemon.to_string()]);
    table.add_row(vec!["default_timeout", &config.default_timeout.to_string()]);
    table.add_row(vec!["default_output_format", &format!("{:?}", config.default_output_format).to_lowercase()]);
    table.add_row(vec!["desktop.screenshot_delay_ms", &config.desktop.screenshot_delay_ms.to_string()]);
    table.add_row(vec!["desktop.click_interval_ms", &config.desktop.click_interval_ms.to_string()]);
    table.add_row(vec!["desktop.ocr_confidence_threshold", &config.desktop.ocr_confidence_threshold.to_string()]);
    table.add_row(vec!["desktop.window_match_strategy", &config.desktop.window_match_strategy]);
    
    println!("{}", table);
    
    println!();
    println!("Config file: {:?}", default_config_path()?);
    
    Ok(())
}

pub fn init(force: bool) -> Result<()> {
    let config_path = init_default_config(force)?;
    
    println!("{} Initialized default configuration", "✓".green());
    println!("  Path: {:?}", config_path);
    println!();
    println!("{}", "Edit this file to customize settings.".dimmed());
    
    Ok(())
}

pub fn path() -> Result<()> {
    let config_path = default_config_path()?;
    
    println!("{}", config_path.display());
    
    Ok(())
}
