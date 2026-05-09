use crate::config::Config;
use crate::ipc::ApiClient;
use crate::models::*;
use anyhow::{Result, Context};
use colored::*;
use comfy_table::{Table, ContentArrangement};

pub async fn create(
    config: &Config,
    query: String,
    watch: bool,
    timeout: u64,
    output_format: &str,
) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        if config.auto_start_daemon {
            println!("{} Supervisor not running, starting daemon...", "INFO:".blue());
            super::daemon::start(config, false, true).await?;
            
            // Wait for daemon to be ready
            tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
        } else {
            anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
        }
    }
    
    // Create task
    let response = client.create_task(&query).await?;
    
    match output_format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&response)?);
        }
        _ => {
            println!("{} Created task {}", "✓".green(), response.task_id.cyan());
            println!("  Status: {}", format_status(&response.status));
            
            if watch {
                println!("\n{} Watching task execution...", "▶".blue());
                watch_task(&client, &response.task_id, timeout).await?;
            } else {
                println!("\n  Use 'agentos task get {}' to check status", response.task_id);
                println!("  Use 'agentos task logs {} --follow' to watch logs", response.task_id);
            }
        }
    }
    
    Ok(())
}

pub async fn list(
    config: &Config,
    status: Option<String>,
    limit: usize,
    output_format: &str,
) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    let response = client.list_tasks(status.as_deref(), limit).await?;
    
    match output_format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&response)?);
        }
        _ => {
            if response.tasks.is_empty() {
                println!("{} No tasks found", "INFO:".blue());
                return Ok(());
            }
            
            let mut table = Table::new();
            table.set_content_arrangement(ContentArrangement::Dynamic);
            table.set_header(vec![
                "ID".bold(),
                "Query".bold(),
                "Status".bold(),
                "Created".bold(),
            ]);
            
            for task in &response.tasks {
                table.add_row(vec![
                    task.id[..8].to_string().dimmed().to_string(),
                    truncate(&task.query, 40),
                    format_status(&task.status),
                    format_time(&task.created_at),
                ]);
            }
            
            println!("{}", table);
            println!("\nShowing {} of {} tasks", response.tasks.len(), response.total);
        }
    }
    
    Ok(())
}

pub async fn get(config: &Config, id: String, output_format: &str) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    let task = client.get_task(&id).await?;
    
    match output_format {
        "json" => {
            println!("{}", serde_json::to_string_pretty(&task)?);
        }
        _ => {
            println!("{}", "Task Details".bold().underline());
            println!("  ID:          {}", task.id.cyan());
            println!("  Query:       {}", task.query);
            println!("  Status:      {}", format_status(&task.status));
            println!("  Created:     {}", format_time(&task.created_at));
            println!("  Updated:     {}", format_time(&task.updated_at));
            
            if let Some(completed) = &task.completed_at {
                println!("  Completed:   {}", format_time(completed));
            }
            
            if let Some(result) = &task.result {
                println!("  Result:      {}", result.green());
            }
            
            if let Some(error) = &task.error {
                println!("  Error:       {}", error.red());
            }
            
            if !task.steps.is_empty() {
                println!("\n{}", "Steps:".bold());
                for (i, step) in task.steps.iter().enumerate() {
                    let status_icon = match step.status {
                        StepStatus::Completed => "✓".green(),
                        StepStatus::Running => "▶".blue(),
                        StepStatus::Failed => "✗".red(),
                        StepStatus::Skipped => "⊘".dimmed(),
                        StepStatus::Pending => "○".dimmed(),
                    };
                    println!("  {} {} {}", status_icon, i + 1, step.description);
                }
            }
        }
    }
    
    Ok(())
}

pub async fn cancel(config: &Config, id: String) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    client.cancel_task(&id).await?;
    
    println!("{} Cancelled task {}", "✓".green(), id.cyan());
    
    Ok(())
}

pub async fn logs(config: &Config, id: String, follow: bool, tail: usize) -> Result<()> {
    let client = ApiClient::new(config);
    
    // Check if supervisor is running
    if !client.health_check().await? {
        anyhow::bail!("Supervisor is not running. Use 'agentos daemon start' to start it.");
    }
    
    if follow {
        println!("{} Following logs for task {} (Press Ctrl+C to stop)...", "▶".blue(), id.cyan());
        println!();
        
        let mut last_lines = 0;
        
        loop {
            match client.get_task_logs(&id, tail).await {
                Ok(logs) => {
                    // Print only new lines
                    if logs.len() > last_lines {
                        for line in &logs[last_lines..] {
                            println!("{}", line);
                        }
                        last_lines = logs.len();
                    }
                }
                Err(e) => {
                    eprintln!("{} Error fetching logs: {}", "ERROR:".red(), e);
                }
            }
            
            tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
        }
    } else {
        let logs = client.get_task_logs(&id, tail).await?;
        
        for line in &logs {
            println!("{}", line);
        }
    }
    
    Ok(())
}

async fn watch_task(client: &ApiClient, task_id: &str, timeout: u64) -> Result<()> {
    let start = std::time::Instant::now();
    let mut last_status: Option<TaskStatus> = None;
    
    loop {
        let task = client.get_task(task_id).await?;
        
        // Print status change
        if last_status.as_ref() != Some(&task.status) {
            println!("  Status: {} → {}", 
                last_status.as_ref().map(|s| format!("{}", s)).unwrap_or_else(|| "created".to_string()).dimmed(),
                format_status(&task.status)
            );
            last_status = Some(task.status.clone());
        }
        
        // Check if task is complete
        match task.status {
            TaskStatus::Completed => {
                println!("\n{} Task completed successfully", "✓".green().bold());
                if let Some(result) = &task.result {
                    println!("  Result: {}", result);
                }
                return Ok(());
            }
            TaskStatus::Failed => {
                println!("\n{} Task failed", "✗".red().bold());
                if let Some(error) = &task.error {
                    println!("  Error: {}", error.red());
                }
                return Ok(());
            }
            TaskStatus::Cancelled => {
                println!("\n{} Task was cancelled", "⊘".yellow().bold());
                return Ok(());
            }
            _ => {}
        }
        
        // Check timeout
        if timeout > 0 && start.elapsed().as_secs() > timeout {
            println!("\n{} Timeout reached ({}s)", "⚠".yellow().bold(), timeout);
            return Ok(());
        }
        
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
    }
}

fn format_status(status: &TaskStatus) -> String {
    match status {
        TaskStatus::Pending => "pending".dimmed().to_string(),
        TaskStatus::Running => "running".blue().to_string(),
        TaskStatus::Paused => "paused".yellow().to_string(),
        TaskStatus::Completed => "completed".green().to_string(),
        TaskStatus::Failed => "failed".red().to_string(),
        TaskStatus::Cancelled => "cancelled".yellow().to_string(),
    }
}

fn format_time(dt: &chrono::DateTime<chrono::Utc>) -> String {
    let local = dt.with_timezone(&chrono::Local);
    local.format("%Y-%m-%d %H:%M").to_string()
}

fn truncate(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else {
        format!("{}...", &s[..max_len.saturating_sub(3)])
    }
}
