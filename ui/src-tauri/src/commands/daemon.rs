use std::path::PathBuf;
use std::time::Duration;
use sysinfo::{ProcessRefreshKind, RefreshKind, System};
use tauri::AppHandle;
use tokio::time::sleep;

use agentos_ipc_client::KernelClient;

/// Daemon status information returned to the frontend
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DaemonStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub uptime_secs: Option<u64>,
    pub version: Option<String>,
    pub active_tasks: i32,
    pub error: Option<String>,
}

/// Result of a daemon operation
#[derive(Debug, Clone, serde::Serialize)]
pub struct DaemonOperationResult {
    pub success: bool,
    pub message: String,
}

/// Get the supervisor binary name based on the platform
fn get_supervisor_binary_name() -> &'static str {
    #[cfg(target_os = "windows")]
    {
        "supervisor.exe"
    }
    #[cfg(not(target_os = "windows"))]
    {
        "supervisor"
    }
}

/// Check if a process name matches the supervisor binary
fn is_supervisor_process(process: &sysinfo::Process) -> bool {
    if let Some(exe) = process.exe() {
        let exe_name = exe
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        let expected_name = get_supervisor_binary_name().to_lowercase();

        if exe_name == expected_name {
            return true;
        }

        let exe_str = exe.to_string_lossy().to_lowercase();
        if exe_str.contains("binaries") && exe_str.contains("supervisor") {
            return true;
        }
    }

    let cmd = process.cmd().join(" ");
    if cmd.contains("supervisor") && !cmd.contains("agentos-tauri") {
        return true;
    }

    false
}

/// Find the supervisor process and return its PID and uptime
fn find_supervisor_process() -> Option<(u32, u64)> {
    let mut system = System::new_with_specifics(
        RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
    );
    system.refresh_processes();

    for (pid, process) in system.processes() {
        if is_supervisor_process(process) {
            return Some((pid.as_u32(), process.run_time()));
        }
    }
    None
}

/// Get daemon status via gRPC health check
#[tauri::command]
pub async fn get_daemon_status() -> Result<DaemonStatus, String> {
    let process_info = find_supervisor_process();

    // Try gRPC health check
    match KernelClient::connect().await {
        Ok(mut client) => match client.health_check().await {
            Ok(resp) => {
                let running = resp.healthy;
                Ok(DaemonStatus {
                    running,
                    pid: process_info.map(|(pid, _)| pid),
                    uptime_secs: process_info.map(|(_, uptime)| uptime),
                    version: Some(resp.version),
                    active_tasks: 0,
                    error: if running {
                        None
                    } else {
                        Some("Kernel not healthy".to_string())
                    },
                })
            }
            Err(e) => Ok(DaemonStatus {
                running: false,
                pid: process_info.map(|(pid, _)| pid),
                uptime_secs: None,
                version: None,
                active_tasks: 0,
                error: Some(format!("Health check failed: {}", e)),
            }),
        },
        Err(_) => Ok(DaemonStatus {
            running: false,
            pid: None,
            uptime_secs: None,
            version: None,
            active_tasks: 0,
            error: None,
        }),
    }
}

/// Start the kernel daemon
#[tauri::command]
pub async fn start_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    // Check if already running
    let status = get_daemon_status().await?;
    if status.running {
        return Ok(status);
    }

    // Determine supervisor binary path
    let supervisor_bin = resolve_supervisor_binary(&app_handle)?;

    // Spawn the supervisor process
    tokio::process::Command::new(&supervisor_bin)
        .env("AGENTOS_RUNTIME_MODE", "grpc")
        .env(
            "AGENTOS_DATA_DIR",
            get_data_dir().to_string_lossy().as_ref(),
        )
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| {
            format!(
                "Failed to start supervisor '{}': {}",
                supervisor_bin.display(),
                e
            )
        })?;

    // Wait for supervisor to become healthy via gRPC
    for _ in 0..150 {
        sleep(Duration::from_millis(200)).await;
        if let Ok(mut client) = KernelClient::connect().await {
            if let Ok(resp) = client.health_check().await {
                if resp.healthy {
                    return get_daemon_status().await;
                }
            }
        }
    }

    Err("Supervisor started but did not become healthy within 30 seconds".to_string())
}

/// Resolve the supervisor binary path
fn resolve_supervisor_binary(app_handle: &AppHandle) -> Result<PathBuf, String> {
    let binary_name = get_supervisor_binary_name();

    // Try bundled resource first
    let bundled_path = app_handle
        .path_resolver()
        .resolve_resource(format!("binaries/{}", binary_name));

    if let Some(path) = bundled_path {
        if path.exists() {
            return Ok(path);
        }
    }

    // Try PATH
    if let Ok(path) = which::which(binary_name) {
        return Ok(path);
    }

    // Fallback to current directory
    let cwd_binary = PathBuf::from(binary_name);
    if cwd_binary.exists() {
        return Ok(cwd_binary);
    }

    Err(format!(
        "Could not find supervisor binary '{}'. Please ensure AgentOS is properly installed.",
        binary_name
    ))
}

/// Get the data directory path
fn get_data_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("AgentOS")
}

/// Stop the kernel daemon via gRPC shutdown RPC
#[tauri::command]
pub async fn stop_daemon() -> Result<DaemonStatus, String> {
    match KernelClient::connect().await {
        Ok(mut client) => {
            let _ = client.shutdown(true, 10).await;
        }
        Err(_) => {
            // Not running, nothing to stop
        }
    }

    sleep(Duration::from_secs(2)).await;

    get_daemon_status().await
}

/// Restart the kernel daemon
#[tauri::command]
pub async fn restart_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    let _ = stop_daemon().await;
    sleep(Duration::from_secs(2)).await;
    start_daemon(app_handle).await
}

/// Check if the daemon is installed and available
#[tauri::command]
pub async fn check_daemon_installation(
    app_handle: AppHandle,
) -> Result<DaemonOperationResult, String> {
    match resolve_supervisor_binary(&app_handle) {
        Ok(path) => Ok(DaemonOperationResult {
            success: true,
            message: format!("Supervisor found at: {}", path.display()),
        }),
        Err(e) => Ok(DaemonOperationResult {
            success: false,
            message: e,
        }),
    }
}
