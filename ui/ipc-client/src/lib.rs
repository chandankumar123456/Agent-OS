//! Shared IPC client for AgentOS UI crates.
//!
//! Provides a `KernelClient` that communicates with the AgentOS kernel
//! over gRPC using Unix domain sockets (POSIX), named pipes (Windows),
//! or TCP localhost as a fallback.

use std::path::PathBuf;

use anyhow::{Context, Result};
use tonic::transport::{Channel, Endpoint, Uri};
use tower::service_fn;
use tracing::debug;

// Re-export protocol types for convenience
pub use agentos_ipc_protocol::runtime;
pub use agentos_ipc_protocol::runtime::runtime_service_client::RuntimeServiceClient;

/// Environment variable for overriding the IPC socket path.
const ENV_IPC_SOCKET: &str = "AGENTOS_IPC_SOCKET";

/// Default TCP fallback address.
const DEFAULT_TCP_ADDR: &str = "http://127.0.0.1:50051";

/// Transport mode for the IPC connection.
#[derive(Debug, Clone)]
pub enum Transport {
    /// Unix domain socket (Linux/macOS)
    #[cfg(unix)]
    Unix(PathBuf),
    /// TCP connection (fallback on all platforms)
    Tcp(String),
}

/// Resolve the transport to use based on environment and platform.
pub fn resolve_transport() -> Transport {
    // Check environment variable first
    if let Ok(socket_path) = std::env::var(ENV_IPC_SOCKET) {
        let path = PathBuf::from(&socket_path);
        #[cfg(unix)]
        {
            if path.exists() || !socket_path.starts_with("http") {
                return Transport::Unix(path);
            }
        }
        #[cfg(not(unix))]
        {
            let _ = path;
        }
        // If it looks like a URL, use TCP
        if socket_path.starts_with("http") {
            return Transport::Tcp(socket_path);
        }
    }

    // Try default UDS path on Unix
    #[cfg(unix)]
    {
        let default_sock = default_socket_path();
        if default_sock.exists() {
            return Transport::Unix(default_sock);
        }
    }

    // Fallback to TCP
    Transport::Tcp(DEFAULT_TCP_ADDR.to_string())
}

/// Default UDS path: ~/.agentos/ipc.sock
#[cfg(unix)]
fn default_socket_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join(".agentos")
        .join("ipc.sock")
}

/// Connect to the kernel and return a gRPC channel.
pub async fn connect() -> Result<Channel> {
    let transport = resolve_transport();
    debug!(?transport, "Connecting to kernel");

    match transport {
        #[cfg(unix)]
        Transport::Unix(path) => connect_unix(path).await,
        Transport::Tcp(addr) => connect_tcp(&addr).await,
    }
}

/// Connect via TCP.
async fn connect_tcp(addr: &str) -> Result<Channel> {
    let channel = Endpoint::from_shared(addr.to_string())
        .context("invalid TCP endpoint")?
        .connect()
        .await
        .context("failed to connect via TCP")?;
    Ok(channel)
}

/// Connect via Unix domain socket.
#[cfg(unix)]
async fn connect_unix(path: PathBuf) -> Result<Channel> {
    let channel = Endpoint::try_from("http://[::]:50051")
        .context("failed to create UDS endpoint")?
        .connect_with_connector(service_fn(move |_: Uri| {
            let path = path.clone();
            async move { tokio::net::UnixStream::connect(path).await }
        }))
        .await
        .context("failed to connect via Unix socket")?;
    Ok(channel)
}

/// High-level client wrapping the kernel gRPC service.
///
/// All methods are thin forwarders to the kernel RPCs with no business logic.
#[derive(Clone)]
pub struct KernelClient {
    inner: RuntimeServiceClient<Channel>,
}

impl KernelClient {
    /// Create a new KernelClient by connecting to the kernel.
    pub async fn connect() -> Result<Self> {
        let channel = connect().await?;
        let inner = RuntimeServiceClient::new(channel);
        Ok(Self { inner })
    }

    /// Create a KernelClient from an existing channel.
    pub fn from_channel(channel: Channel) -> Self {
        let inner = RuntimeServiceClient::new(channel);
        Self { inner }
    }

    /// Health check.
    pub async fn health_check(&mut self) -> Result<runtime::HealthCheckResponse> {
        let resp = self
            .inner
            .health_check(runtime::HealthCheckRequest {})
            .await
            .context("health_check RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Get runtime status.
    pub async fn get_status(
        &mut self,
        include_metrics: bool,
    ) -> Result<runtime::RuntimeStatus> {
        let resp = self
            .inner
            .get_runtime_status(runtime::GetRuntimeStatusRequest { include_metrics })
            .await
            .context("get_runtime_status RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Create a new task.
    pub async fn create_task(
        &mut self,
        query: &str,
        timeout_seconds: i32,
    ) -> Result<runtime::CreateTaskResponse> {
        let resp = self
            .inner
            .create_task(runtime::CreateTaskRequest {
                query: query.to_string(),
                r#type: 0, // UNSPECIFIED, kernel decides
                require_approval: false,
                timeout_seconds,
                parent_task_id: String::new(),
                config: Default::default(),
            })
            .await
            .context("create_task RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Get a task by ID.
    pub async fn get_task(&mut self, task_id: &str) -> Result<runtime::GetTaskResponse> {
        let resp = self
            .inner
            .get_task(runtime::GetTaskRequest {
                task_id: task_id.to_string(),
            })
            .await
            .context("get_task RPC failed")?;
        Ok(resp.into_inner())
    }

    /// List tasks.
    pub async fn list_tasks(
        &mut self,
        filter_status: i32,
        limit: i32,
        offset: i32,
    ) -> Result<runtime::ListTasksResponse> {
        let resp = self
            .inner
            .list_tasks(runtime::ListTasksRequest {
                filter_status,
                limit,
                offset,
                include_completed: true,
            })
            .await
            .context("list_tasks RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Cancel a task.
    pub async fn cancel_task(
        &mut self,
        task_id: &str,
        reason: &str,
    ) -> Result<runtime::CancelTaskResponse> {
        let resp = self
            .inner
            .cancel_task(runtime::CancelTaskRequest {
                task_id: task_id.to_string(),
                reason: reason.to_string(),
            })
            .await
            .context("cancel_task RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Stream task events.
    pub async fn stream_events(
        &mut self,
        task_id: &str,
        include_history: bool,
    ) -> Result<tonic::Streaming<runtime::TaskEvent>> {
        let resp = self
            .inner
            .stream_task_events(runtime::TaskEventRequest {
                task_id: task_id.to_string(),
                include_history,
            })
            .await
            .context("stream_task_events RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Shutdown the runtime.
    pub async fn shutdown(
        &mut self,
        graceful: bool,
        timeout_seconds: i32,
    ) -> Result<runtime::ShutdownResponse> {
        let resp = self
            .inner
            .shutdown(runtime::ShutdownRequest {
                graceful,
                timeout_seconds,
            })
            .await
            .context("shutdown RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Get configuration.
    pub async fn get_config(&mut self, key: &str) -> Result<runtime::GetConfigResponse> {
        let resp = self
            .inner
            .get_config(runtime::GetConfigRequest {
                key: key.to_string(),
            })
            .await
            .context("get_config RPC failed")?;
        Ok(resp.into_inner())
    }

    /// Set configuration.
    pub async fn set_config(
        &mut self,
        key: &str,
        value: &str,
    ) -> Result<runtime::SetConfigResponse> {
        let resp = self
            .inner
            .set_config(runtime::SetConfigRequest {
                key: key.to_string(),
                value: value.to_string(),
            })
            .await
            .context("set_config RPC failed")?;
        Ok(resp.into_inner())
    }
}
