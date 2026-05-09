use crate::config::Config;
use crate::ipc::ApiClient;
use anyhow::{Result, Context};
use colored::*;
use std::fs;

pub async fn screenshot(config: &Config, output: Option<String>, window: Option<String>) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    println!("{} Taking screenshot...", "▶".blue());
    
    let screenshot = client.take_screenshot(window.as_deref()).await?;
    
    // Determine output path
    let output_path = if let Some(path) = output {
        path
    } else {
        let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
        format!("screenshot_{}.png", timestamp)
    };
    
    // Save screenshot
    fs::write(&output_path, screenshot)
        .context("Failed to save screenshot")?;
    
    println!("{} Screenshot saved to {}", "✓".green(), output_path.cyan());
    
    Ok(())
}

pub async fn click(config: &Config, x: i32, y: i32, button: String, clicks: u32) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    println!("{} Clicking at ({}, {}) with {} button ({} click(s))...", 
        "▶".blue(), x, y, button, clicks);
    
    client.click(x, y, &button, clicks).await?;
    
    println!("{} Click completed", "✓".green());
    
    Ok(())
}

pub async fn type_text(config: &Config, text: String, interval: u64) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    println!("{} Typing text ({} chars, {}ms interval)...", 
        "▶".blue(), text.len(), interval);
    
    client.type_text(&text, interval).await?;
    
    println!("{} Text typed successfully", "✓".green());
    
    Ok(())
}

pub async fn focus(config: &Config, window: String) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    println!("{} Focusing window '{}'...", "▶".blue(), window);
    
    client.focus_window(&window).await?;
    
    println!("{} Window focused", "✓".green());
    
    Ok(())
}

pub async fn list_windows(config: &Config, filter: Option<String>, output_format: &str) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    let windows = client.list_windows(filter.as_deref()).await?;
    
    match output_format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&windows)?);
        }
        _ => {
            if windows.is_empty() {
                println!("{} No windows found", "INFO:".blue());
                return Ok(());
            }
            
            use comfy_table::{Table, ContentArrangement};
            
            let mut table = Table::new();
            table.set_content_arrangement(ContentArrangement::Dynamic);
            table.set_header(vec![
                "ID".bold(),
                "Title".bold(),
                "Process".bold(),
                "PID".bold(),
                "Position".bold(),
                "Size".bold(),
            ]);
            
            for window in &windows {
                let pos = format!("{}, {}", window.rect.x, window.rect.y);
                let size = format!("{}x{}", window.rect.width, window.rect.height);
                
                table.add_row(vec![
                    window.id.to_string().dimmed().to_string(),
                    truncate(&window.title, 30),
                    truncate(&window.process_name, 15),
                    window.pid.to_string(),
                    pos,
                    size,
                ]);
            }
            
            println!("{}", table);
            println!("\nFound {} windows", windows.len());
        }
    }
    
    Ok(())
}

pub async fn find(config: &Config, text: String, screenshot: bool) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    if screenshot {
        println!("{} Taking screenshot and searching for '{}'...", "▶".blue(), text);
    } else {
        println!("{} Searching for '{}'...", "▶".blue(), text);
    }
    
    match client.find_element(&text).await? {
        Some(element) => {
            println!("{} Found '{}' at ({}, {})", 
                "✓".green(), 
                element.text,
                element.rect.x,
                element.rect.y
            );
            println!("  Confidence: {:.1}%", element.confidence * 100.0);
            println!("  Size: {}x{}", element.rect.width, element.rect.height);
        }
        None => {
            println!("{} Could not find '{}' on screen", "✗".red(), text);
        }
    }
    
    Ok(())
}

fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        format!("{}...", &s[..max_len.saturating_sub(3)])
    }
}
