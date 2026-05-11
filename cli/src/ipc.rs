use reqwest::Client;
use anyhow::{Result, Context};
use crate::config::Config;
use crate::models::*;

pub struct ApiClient {
    client: Client,
    base_url: String,
}

impl ApiClient {
    pub fn new(config: &Config) -> Self {
        Self {
            client: Client::new(),
            base_url: config.supervisor_url(),
        }
    }

    /// Check if supervisor is running
    pub async fn health_check(&self) -> Result<bool> {
        let url = format!("{}/health", self.base_url);
        match self.client.get(&url).send().await {
            Ok(response) => Ok(response.status().is_success()),
            Err(_) => Ok(false),
        }
    }

    /// Get daemon status
    pub async fn get_status(&self) -> Result<DaemonStatus> {
        let url = format!("{}/status", self.base_url);
        let response = self.client
            .get(&url)
            .send()
            .await
            .context("Failed to connect to supervisor")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to get status: {}", text);
        }
        
        let status: DaemonStatus = response
            .json()
            .await
            .context("Failed to parse status response")?;
        
        Ok(status)
    }

    /// Stop Python runtime
    pub async fn stop_python(&self) -> Result<()> {
        let url = format!("{}/api/v1/python/stop", self.base_url);
        let response = self.client
            .post(&url)
            .send()
            .await
            .context("Failed to send stop request")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to stop Python runtime: {}", text);
        }
        
        Ok(())
    }

    /// Create a new task
    pub async fn create_task(&self, query: &str) -> Result<CreateTaskResponse> {
        let url = format!("{}/api/v1/tasks", self.base_url);
        let request = CreateTaskRequest {
            query: query.to_string(),
        };
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to create task")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to create task: {}", text);
        }
        
        let result: CreateTaskResponse = response
            .json()
            .await
            .context("Failed to parse task response")?;
        
        Ok(result)
    }

    /// List tasks
    pub async fn list_tasks(&self, status: Option<&str>, limit: usize) -> Result<ListTasksResponse> {
        let mut url = format!("{}/api/v1/tasks?limit={}", self.base_url, limit);
        
        if let Some(s) = status {
            url.push_str(&format!("&status={}", s));
        }
        
        let response = self.client
            .get(&url)
            .send()
            .await
            .context("Failed to list tasks")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to list tasks: {}", text);
        }
        
        let result: ListTasksResponse = response
            .json()
            .await
            .context("Failed to parse tasks response")?;
        
        Ok(result)
    }

    /// Get task details
    pub async fn get_task(&self, task_id: &str) -> Result<Task> {
        let url = format!("{}/api/v1/tasks/{}", self.base_url, task_id);
        
        let response = self.client
            .get(&url)
            .send()
            .await
            .context("Failed to get task")?;
        
        if response.status() == 404 {
            anyhow::bail!("Task not found: {}", task_id);
        }
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to get task: {}", text);
        }
        
        let result: Task = response
            .json()
            .await
            .context("Failed to parse task response")?;
        
        Ok(result)
    }

    /// Cancel a task
    pub async fn cancel_task(&self, task_id: &str) -> Result<()> {
        let url = format!("{}/api/v1/tasks/{}/cancel", self.base_url, task_id);
        
        let response = self.client
            .post(&url)
            .send()
            .await
            .context("Failed to cancel task")?;
        
        if response.status() == 404 {
            anyhow::bail!("Task not found: {}", task_id);
        }
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to cancel task: {}", text);
        }
        
        Ok(())
    }

    /// Get task logs
    pub async fn get_task_logs(&self, task_id: &str, tail: usize) -> Result<Vec<String>> {
        let url = format!("{}/api/v1/tasks/{}/logs?tail={}", self.base_url, task_id, tail);
        
        let response = self.client
            .get(&url)
            .send()
            .await
            .context("Failed to get task logs")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to get task logs: {}", text);
        }
        
        let logs: Vec<String> = response
            .json()
            .await
            .context("Failed to parse logs response")?;
        
        Ok(logs)
    }

    /// Take screenshot
    pub async fn take_screenshot(&self, window: Option<&str>) -> Result<Vec<u8>> {
        let mut url = format!("{}/api/v1/desktop/screenshot", self.base_url);
        
        if let Some(w) = window {
            url.push_str(&format!("?window={}", w));
        }
        
        let response = self.client
            .get(&url)
            .send()
            .await
            .context("Failed to take screenshot")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to take screenshot: {}", text);
        }
        
        let bytes = response.bytes().await.context("Failed to read screenshot")?;
        Ok(bytes.to_vec())
    }

    /// Click at coordinates
    pub async fn click(&self, x: i32, y: i32, button: &str, clicks: u32) -> Result<()> {
        let url = format!("{}/api/v1/desktop/click", self.base_url);
        
        #[derive(serde::Serialize)]
        struct ClickRequest {
            x: i32,
            y: i32,
            button: String,
            clicks: u32,
        }
        
        let request = ClickRequest {
            x,
            y,
            button: button.to_string(),
            clicks,
        };
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send click request")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to click: {}", text);
        }
        
        Ok(())
    }

    /// Type text
    pub async fn type_text(&self, text: &str, interval_ms: u64) -> Result<()> {
        let url = format!("{}/api/v1/desktop/type", self.base_url);
        
        #[derive(serde::Serialize)]
        struct TypeRequest {
            text: String,
            interval_ms: u64,
        }
        
        let request = TypeRequest {
            text: text.to_string(),
            interval_ms,
        };
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send type request")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to type text: {}", text);
        }
        
        Ok(())
    }

    /// Focus window
    pub async fn focus_window(&self, title: &str) -> Result<()> {
        let url = format!("{}/api/v1/desktop/focus", self.base_url);
        
        #[derive(serde::Serialize)]
        struct FocusRequest {
            title: String,
        }
        
        let request = FocusRequest {
            title: title.to_string(),
        };
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send focus request")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to focus window: {}", text);
        }
        
        Ok(())
    }

    /// List windows
    pub async fn list_windows(&self, filter: Option<&str>) -> Result<Vec<WindowInfo>> {
        let mut url = format!("{}/api/v1/desktop/windows", self.base_url);
        
        if let Some(f) = filter {
            url.push_str(&format!("?filter={}", f));
        }
        
        let response = self.client
            .get(&url)
            .send()
            .await
            .context("Failed to list windows")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to list windows: {}", text);
        }
        
        let windows: Vec<WindowInfo> = response
            .json()
            .await
            .context("Failed to parse windows response")?;
        
        Ok(windows)
    }

    /// Find element on screen
    pub async fn find_element(&self, text: &str) -> Result<Option<ScreenElement>> {
        let url = format!("{}/api/v1/desktop/find", self.base_url);
        
        #[derive(serde::Serialize)]
        struct FindRequest {
            text: String,
        }
        
        let request = FindRequest {
            text: text.to_string(),
        };
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .context("Failed to send find request")?;
        
        if !response.status().is_success() {
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("Failed to find element: {}", text);
        }
        
        let element: Option<ScreenElement> = response
            .json()
            .await
            .context("Failed to parse find response")?;
        
        Ok(element)
    }
}
