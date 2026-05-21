use agentos_ipc_client::KernelClient;
use anyhow::{Context, Result};
use crate::models::*;

pub struct ApiClient {
    client: Option<KernelClient>,
}

impl ApiClient {
    pub fn new() -> Self {
        Self { client: None }
    }

    async fn get_client(&mut self) -> Result<&mut KernelClient> {
        if self.client.is_none() {
            let client = KernelClient::connect()
                .await
                .context("Failed to connect to kernel")?;
            self.client = Some(client);
        }
        Ok(self.client.as_mut().unwrap())
    }

    /// Check if the kernel is reachable
    pub async fn health_check(&mut self) -> Result<bool> {
        match self.get_client().await {
            Ok(client) => match client.health_check().await {
                Ok(resp) => Ok(resp.healthy),
                Err(_) => Ok(false),
            },
            Err(_) => Ok(false),
        }
    }

    /// Get daemon/runtime status
    pub async fn get_status(&mut self) -> Result<DaemonStatus> {
        let client = self.get_client().await?;
        let status = client
            .get_status(true)
            .await
            .context("Failed to get runtime status")?;

        Ok(DaemonStatus {
            running: true,
            pid: None,
            version: status.version.clone(),
            uptime_seconds: status.uptime.as_ref().map(|t| t.seconds as u64),
            active_tasks: status.active_tasks as usize,
            total_tasks: (status.completed_tasks + status.failed_tasks + status.active_tasks + status.queued_tasks) as usize,
            memory_usage_mb: status.metrics.as_ref().map(|m| m.memory_bytes as f64 / 1_048_576.0),
            last_health_check: None,
        })
    }

    /// Shutdown the runtime (replaces stop_python)
    pub async fn stop_runtime(&mut self) -> Result<()> {
        let client = self.get_client().await?;
        client.shutdown(true, 30).await?;
        Ok(())
    }

    /// Create a new task
    pub async fn create_task(&mut self, query: &str) -> Result<CreateTaskResponse> {
        let client = self.get_client().await?;
        let resp = client.create_task(query, 0).await?;

        let task_status = if resp.success {
            TaskStatus::Pending
        } else {
            TaskStatus::Failed
        };

        let task_id = resp
            .task
            .as_ref()
            .map(|t| t.id.clone())
            .unwrap_or_default();

        Ok(CreateTaskResponse {
            task_id,
            status: task_status,
        })
    }

    /// List tasks
    pub async fn list_tasks(&mut self, status: Option<&str>, limit: usize) -> Result<ListTasksResponse> {
        let filter_status = match status {
            Some("pending") => 1,
            Some("running") => 3,
            Some("completed") => 6,
            Some("failed") => 7,
            Some("cancelled") => 8,
            _ => 0,
        };

        let client = self.get_client().await?;
        let resp = client
            .list_tasks(filter_status, limit as i32, 0)
            .await?;

        let tasks: Vec<Task> = resp
            .tasks
            .into_iter()
            .map(proto_task_to_model)
            .collect();

        Ok(ListTasksResponse {
            total: resp.total_count as usize,
            tasks,
        })
    }

    /// Get task details
    pub async fn get_task(&mut self, task_id: &str) -> Result<Task> {
        let client = self.get_client().await?;
        let resp = client.get_task(task_id).await?;

        if !resp.success {
            anyhow::bail!("Failed to get task: {}", resp.error);
        }

        let task = resp
            .task
            .map(proto_task_to_model)
            .context("Task not found")?;

        Ok(task)
    }

    /// Cancel a task
    pub async fn cancel_task(&mut self, task_id: &str) -> Result<()> {
        let client = self.get_client().await?;
        let resp = client.cancel_task(task_id, "Cancelled by user").await?;

        if !resp.success {
            anyhow::bail!("Failed to cancel task: {}", resp.error);
        }

        Ok(())
    }

    /// Stream task events (returns a stream)
    pub async fn stream_events(
        &mut self,
        task_id: &str,
    ) -> Result<tonic::Streaming<agentos_ipc_client::runtime::TaskEvent>> {
        let client = self.get_client().await?;
        client.stream_events(task_id, true).await
    }
}

/// Convert a proto Task to our local model Task.
fn proto_task_to_model(t: agentos_ipc_client::runtime::Task) -> Task {
    use chrono::{DateTime, Utc};

    let status = match t.status {
        1 => TaskStatus::Pending,
        2..=4 => TaskStatus::Running,
        5 => TaskStatus::Paused,
        6 => TaskStatus::Completed,
        7 => TaskStatus::Failed,
        8 => TaskStatus::Cancelled,
        _ => TaskStatus::Pending,
    };

    let to_dt = |ts: Option<prost_types::Timestamp>| -> DateTime<Utc> {
        ts.and_then(|t| DateTime::from_timestamp(t.seconds, t.nanos as u32))
            .unwrap_or_default()
    };

    Task {
        id: t.id,
        query: t.query,
        status,
        created_at: to_dt(t.created_at),
        updated_at: to_dt(t.updated_at),
        completed_at: t.completed_at.and_then(|ts| DateTime::from_timestamp(ts.seconds, ts.nanos as u32)),
        steps: Vec::new(),
        result: if t.result.is_empty() { None } else { Some(t.result) },
        error: if t.error.is_empty() { None } else { Some(t.error) },
    }
}
