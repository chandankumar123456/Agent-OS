use crate::config::Config;
use crate::ipc::ApiClient;
use crate::models::*;
use anyhow::Result;
use colored::*;
use comfy_table::{ContentArrangement, Table};

pub async fn create(
    _config: &Config,
    query: String,
    watch: bool,
    _timeout: u64,
    output_format: &str,
) -> Result<()> {
    let mut client = ApiClient::new();

    // Check if kernel is running
    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
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
                watch_task(&mut client, &response.task_id).await?;
            } else {
                println!(
                    "\n  Use 'agentos task get {}' to check status",
                    response.task_id
                );
                println!(
                    "  Use 'agentos task logs {} --follow' to watch logs",
                    response.task_id
                );
            }
        }
    }

    Ok(())
}

pub async fn list(
    _config: &Config,
    status: Option<String>,
    limit: usize,
    output_format: &str,
) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
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
                let id_str = if task.id.len() > 8 {
                    task.id[..8].to_string()
                } else {
                    task.id.clone()
                };
                table.add_row(vec![
                    id_str.dimmed().to_string(),
                    truncate(&task.query, 40),
                    format_status(&task.status),
                    format_time(&task.created_at),
                ]);
            }

            println!("{}", table);
            println!(
                "\nShowing {} of {} tasks",
                response.tasks.len(),
                response.total
            );
        }
    }

    Ok(())
}

pub async fn get(_config: &Config, id: String, output_format: &str) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
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

pub async fn cancel(_config: &Config, id: String) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    client.cancel_task(&id).await?;

    println!("{} Cancelled task {}", "✓".green(), id.cyan());

    Ok(())
}

pub async fn logs(_config: &Config, id: String, follow: bool, _tail: usize) -> Result<()> {
    let mut client = ApiClient::new();

    if !client.health_check().await? {
        anyhow::bail!("Kernel is not running. Start it with 'python -m core' first.");
    }

    if follow {
        println!(
            "{} Streaming events for task {} (Press Ctrl+C to stop)...",
            "▶".blue(),
            id.cyan()
        );
        println!();

        let mut stream = client.stream_events(&id).await?;
        use tokio_stream::StreamExt;
        while let Some(event) = stream.next().await {
            match event {
                Ok(ev) => {
                    if let Some(log) = ev.log {
                        println!("{}", log.message);
                    }
                }
                Err(e) => {
                    eprintln!("{} Stream error: {}", "ERROR:".red(), e);
                    break;
                }
            }
        }
    } else {
        // Without follow, get the task and display steps as logs
        let task = client.get_task(&id).await?;
        if let Some(result) = &task.result {
            println!("{}", result);
        }
        for step in &task.steps {
            println!("[{}] {}", format_step_status(&step.status), step.description);
            if let Some(result) = &step.result {
                println!("  {}", result);
            }
        }
    }

    Ok(())
}

async fn watch_task(client: &mut ApiClient, task_id: &str) -> Result<()> {
    let mut last_status: Option<TaskStatus> = None;

    loop {
        let task = client.get_task(task_id).await?;

        // Print status change
        if last_status.as_ref() != Some(&task.status) {
            println!(
                "  Status: {} -> {}",
                last_status
                    .as_ref()
                    .map(|s| format!("{}", s))
                    .unwrap_or_else(|| "created".to_string())
                    .dimmed(),
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

fn format_step_status(status: &StepStatus) -> String {
    match status {
        StepStatus::Completed => "done".to_string(),
        StepStatus::Running => "running".to_string(),
        StepStatus::Failed => "failed".to_string(),
        StepStatus::Skipped => "skipped".to_string(),
        StepStatus::Pending => "pending".to_string(),
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
