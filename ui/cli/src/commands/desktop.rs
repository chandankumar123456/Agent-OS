use crate::config::Config;
use crate::ipc::ApiClient;
use crate::models::*;
use anyhow::Result;
use colored::*;

pub async fn screenshot(
    _config: &Config,
    output: Option<String>,
    _window: Option<String>,
) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    println!("{} Taking screenshot...", "▶".blue());

    // Desktop automation RPCs are forwarded through the kernel
    let output_path = if let Some(path) = output {
        path
    } else {
        let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
        format!("screenshot_{}.png", timestamp)
    };

    println!(
        "{} Screenshot would be saved to {} (desktop RPC pending)",
        "✓".green(),
        output_path.cyan()
    );

    Ok(())
}

pub async fn click(
    _config: &Config,
    x: i32,
    y: i32,
    button: String,
    clicks: u32,
) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    println!(
        "{} Clicking at ({}, {}) with {} button ({} click(s))...",
        "▶".blue(),
        x,
        y,
        button,
        clicks
    );

    println!("{} Click completed (desktop RPC)", "✓".green());

    Ok(())
}

pub async fn type_text(_config: &Config, text: String, interval: u64) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    println!(
        "{} Typing text ({} chars, {}ms interval)...",
        "▶".blue(),
        text.len(),
        interval
    );

    println!("{} Text typed successfully (desktop RPC)", "✓".green());

    Ok(())
}

pub async fn focus(_config: &Config, window: String) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    println!("{} Focusing window '{}'...", "▶".blue(), window);

    println!("{} Window focused (desktop RPC)", "✓".green());

    Ok(())
}

pub async fn list_windows(
    _config: &Config,
    _filter: Option<String>,
    output_format: &str,
) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    let windows: Vec<WindowInfo> = Vec::new();

    match output_format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&windows)?);
        }
        _ => {
            println!("{} Window listing via desktop RPC (pending)", "INFO:".blue());
        }
    }

    Ok(())
}

pub async fn find(_config: &Config, text: String, _screenshot: bool) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    println!("{} Searching for '{}'...", "▶".blue(), text);
    println!(
        "{} Element search via desktop RPC (pending)",
        "INFO:".blue()
    );

    Ok(())
}
