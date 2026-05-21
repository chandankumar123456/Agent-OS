use crate::config::Config;
use crate::ipc::ApiClient;
use anyhow::{Context, Result};
use colored::*;
use std::process::Command;

pub async fn start(_config: &Config, background: bool, _auto_start: bool) -> Result<()> {
    let mut client = ApiClient::new();

    if client.health_check().await? {
        println!("{} Kernel is already running", "✓".green());
        return Ok(());
    }

    if background {
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const DETACHED_PROCESS: u32 = 0x00000008;

            Command::new("python")
                .args(["-m", "core"])
                .creation_flags(DETACHED_PROCESS)
                .spawn()
                .context("Failed to start kernel in background")?;
        }

        #[cfg(not(target_os = "windows"))]
        {
            Command::new("python")
                .args(["-m", "core"])
                .spawn()
                .context("Failed to start kernel in background")?;
        }

        println!("{} Started kernel in background", "✓".green());
    } else {
        println!("{} Starting kernel...", "▶".blue());

        let mut child = Command::new("python")
            .args(["-m", "core"])
            .spawn()
            .context("Failed to start kernel")?;

        // Wait for it to be ready
        let mut attempts = 0;
        let max_attempts = 30;

        loop {
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

            if client.health_check().await? {
                println!("{} Kernel is ready", "✓".green());
                break;
            }

            attempts += 1;
            if attempts >= max_attempts {
                child.kill()?;
                anyhow::bail!(
                    "Kernel failed to start within {} seconds",
                    max_attempts / 10
                );
            }

            if let Some(status) = child.try_wait()? {
                anyhow::bail!("Kernel exited with status: {}", status);
            }
        }
    }

    Ok(())
}

pub async fn stop(_config: &Config, _force: bool) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        println!("{} Kernel is not running", "INFO:".blue());
        return Ok(());
    }

    println!("{} Stopping kernel...", "▶".blue());
    match client.stop_runtime().await {
        Ok(_) => println!("{} Kernel stopped", "✓".green()),
        Err(e) => println!("{} Failed to stop kernel: {}", "⚠".yellow(), e),
    }

    Ok(())
}

pub async fn status(_config: &Config, output_format: &str) -> Result<()> {
    let mut client = ApiClient::new();

    match client.get_status().await {
        Ok(status) => match output_format {
            "json" => {
                println!("{}", serde_json::to_string_pretty(&status)?);
            }
            _ => {
                println!("{}", "Daemon Status".bold().underline());
                println!(
                    "  Running:          {}",
                    if status.running {
                        "yes".green()
                    } else {
                        "no".red()
                    }
                );

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
            }
        },
        Err(_) => match output_format {
            "json" => {
                println!("{{\"running\": false}}");
            }
            _ => {
                println!("{} Kernel is not running", "✗".red());
                println!("  Run 'agentos daemon start' to start it");
            }
        },
    }

    Ok(())
}

pub async fn logs(_config: &Config, follow: bool, lines: usize) -> Result<()> {
    let log_path = _config.data_dir.join("logs/kernel.log");

    if !log_path.exists() {
        println!("{} No log file found at {:?}", "INFO:".blue(), log_path);
        return Ok(());
    }

    let content = tokio::fs::read_to_string(&log_path)
        .await
        .context("Failed to read log file")?;

    let log_lines: Vec<&str> = content.lines().collect();
    let start_idx = log_lines.len().saturating_sub(lines);

    for line in &log_lines[start_idx..] {
        println!("{}", line);
    }

    if follow {
        println!(
            "\n{} Following logs (Press Ctrl+C to stop)...",
            "▶".blue()
        );

        let mut last_size = content.len();

        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;

            if let Ok(metadata) = tokio::fs::metadata(&log_path).await {
                let new_size = metadata.len() as usize;
                if new_size > last_size {
                    if let Ok(new_content) = tokio::fs::read_to_string(&log_path).await {
                        let new_lines: Vec<&str> = new_content.lines().collect();
                        let old_line_count = log_lines.len();

                        for line in &new_lines[old_line_count..] {
                            println!("{}", line);
                        }

                        last_size = new_size;
                    }
                }
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
