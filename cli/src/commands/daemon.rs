use crate::config::Config;
use crate::ipc::ApiClient;
use anyhow::{Result, Context};
use colored::*;
use std::process::Command;

pub async fn start(_config: &Config, background: bool, _auto_start: bool) -> Result<()> {
    // Check if already running
    let client = ApiClient::new(_config);
    
    if client.health_check().await? {
        println!("{} Supervisor is already running", "✓".green());
        return Ok(());
    }
    
    if background {
        // Start in background (detached process)
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const DETACHED_PROCESS: u32 = 0x00000008;
            
            Command::new("supervisor.exe")
                .args(&["-data-dir", _config.data_dir.to_str().unwrap()])
                .creation_flags(DETACHED_PROCESS)
                .spawn()
                .context("Failed to start supervisor in background")?;
        }
        
        #[cfg(not(target_os = "windows"))]
        {
            Command::new("supervisor")
                .args(&["-data-dir", _config.data_dir.to_str().unwrap()])
                .spawn()
                .context("Failed to start supervisor in background")?;
        }
        
        println!("{} Started supervisor in background", "✓".green());
    } else {
        // Start in foreground
        println!("{} Starting supervisor...", "▶".blue());
        
        let supervisor_path = std::env::current_exe()?
            .parent()
            .unwrap()
            .join("supervisor.exe");
        
        if !supervisor_path.exists() {
            anyhow::bail!("Supervisor not found at {:?}. Please build it first.", supervisor_path);
        }
        
        let mut child = Command::new(&supervisor_path)
            .args(&[
                "-data-dir", _config.data_dir.to_str().unwrap(),
                "-log-level", &_config.log_level,
            ])
            .spawn()
            .context("Failed to start supervisor")?;
        
        // Wait for it to be ready
        let mut attempts = 0;
        let max_attempts = 30;
        
        loop {
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
            
            if client.health_check().await? {
                println!("{} Supervisor is ready", "✓".green());
                break;
            }
            
            attempts += 1;
            if attempts >= max_attempts {
                child.kill()?;
                anyhow::bail!("Supervisor failed to start within {} seconds", max_attempts / 10);
            }
            
            // Check if process exited
            match child.try_wait()? {
                Some(status) => {
                    anyhow::bail!("Supervisor exited with status: {}", status);
                }
                None => {}
            }
        }
    }
    
    Ok(())
}

pub async fn stop(_config: &Config, force: bool) -> Result<()> {
    let client = ApiClient::new(_config);
    
    if !client.health_check().await? {
        println!("{} Supervisor is not running", "INFO:".blue());
        return Ok(());
    }
    
    // Stop Python runtime first
    println!("{} Stopping Python runtime...", "▶".blue());
    match client.stop_python().await {
        Ok(_) => println!("{} Python runtime stopped", "✓".green()),
        Err(e) => println!("{} Failed to stop Python runtime: {}", "⚠".yellow(), e),
    }
    
    // Stop supervisor
    println!("{} Stopping supervisor...", "▶".blue());
    
    // TODO: Implement graceful shutdown via API
    // For now, we'll need to find and kill the process
    
    #[cfg(target_os = "windows")]
    {
        let args: Vec<&str> = if force { vec!["/F", "/IM", "supervisor.exe"] } else { vec!["/IM", "supervisor.exe"] };
        let _ = Command::new("taskkill")
            .args(&args)
            .output()?;
    }
    
    #[cfg(not(target_os = "windows"))]
    {
        let _ = Command::new("pkill")
            .args(if force { &["-9", "supervisor"] } else { &["supervisor"] })
            .output()?;
    }
    
    println!("{} Supervisor stopped", "✓".green());
    
    Ok(())
}

pub async fn status(config: &Config, output_format: &str) -> Result<()> {
    let client = ApiClient::new(config);
    
    match client.get_status().await {
        Ok(status) => {
            match output_format {
                "json" => {
                    println!("{}", serde_json::to_string_pretty(&status)?);
                }
                _ => {
                    println!("{}", "Daemon Status".bold().underline());
                    println!("  Running:          {}", if status.running { "yes".green() } else { "no".red() });
                    
                    if let Some(pid) = status.pid {
                        println!("  PID:              {}", pid);
                    }
                    
                    println!("  Version:          {}", status.version);
                    
                    if let Some(uptime) = status.uptime_seconds {
                        let hours = uptime / 3600;
                        let minutes = (uptime % 3600) / 60;
                        let seconds = uptime % 60;
                        println!("  Uptime:           {}h {}m {}s", hours, minutes, seconds);
                    }
                    
                    println!("  Active Tasks:     {}", status.active_tasks);
                    println!("  Total Tasks:      {}", status.total_tasks);
                    
                    if let Some(memory) = status.memory_usage_mb {
                        println!("  Memory Usage:     {:.1} MB", memory);
                    }
                    
                    if let Some(last_check) = status.last_health_check {
                        println!("  Last Health Check: {}", last_check);
                    }
                }
            }
        }
        Err(_) => {
            match output_format {
                "json" => {
                    println!("{{\"running\": false}}");
                }
                _ => {
                    println!("{} Supervisor is not running", "✗".red());
                    println!("  Run 'agentos daemon start' to start it");
                }
            }
        }
    }
    
    Ok(())
}

pub async fn logs(_config: &Config, follow: bool, lines: usize) -> Result<()> {
    // Read supervisor logs from file
    let log_path = _config.data_dir.join("logs/supervisor.log");
    
    if !log_path.exists() {
        println!("{} No log file found at {:?}", "INFO:".blue(), log_path);
        return Ok(());
    }
    
    let content = tokio::fs::read_to_string(&log_path).await
        .context("Failed to read log file")?;
    
    let log_lines: Vec<&str> = content.lines().collect();
    let start_idx = log_lines.len().saturating_sub(lines);
    
    for line in &log_lines[start_idx..] {
        println!("{}", line);
    }
    
    if follow {
        println!("\n{} Following logs (Press Ctrl+C to stop)...", "▶".blue());
        
        // TODO: Implement proper log tailing with file watching
        // For now, just poll the file
        let mut last_size = content.len();
        
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
            
            match tokio::fs::metadata(&log_path).await {
                Ok(metadata) => {
                    let new_size = metadata.len() as usize;
                    if new_size > last_size {
                        let new_content = tokio::fs::read_to_string(&log_path).await?;
                        let new_lines: Vec<&str> = new_content.lines().collect();
                        let old_line_count = log_lines.len();
                        
                        for line in &new_lines[old_line_count..] {
                            println!("{}", line);
                        }
                        
                        last_size = new_size;
                    }
                }
                Err(_) => {}
            }
        }
    }
    
    Ok(())
}

pub async fn restart(config: &Config, force: bool) -> Result<()> {
    println!("{} Restarting daemon...", "▶".blue());
    
    stop(config, force).await?;
    tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
    start(config, false, true).await?;
    
    println!("{} Daemon restarted successfully", "✓".green());
    
    Ok(())
}
