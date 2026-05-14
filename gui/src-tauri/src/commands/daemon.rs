use std::path::PathBuf;
use std::time::Duration;
use sysinfo::{ProcessRefreshKind, RefreshKind, System};
use tauri::AppHandle;
use tokio::fs::File;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use tokio::time::{sleep, timeout};

/// Global mutex for storing the daemon child process handle
/// Uses tokio::sync::Mutex for async-safe access
static DAEMON_PROCESS: Mutex<Option<Child>> = const_mutex(None);

/// Supervisor service ports
const SUPERVISOR_GRPC_PORT: u16 = 50051;
const SUPERVISOR_HTTP_PORT: u16 = 8080;

/// Maximum wait time for supervisor to become healthy
const HEALTH_CHECK_TIMEOUT_SECS: u64 = 30;
const HEALTH_CHECK_INTERVAL_MS: u64 = 200;

/// Daemon status information returned to the frontend
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DaemonStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub uptime_secs: Option<u64>,
    pub grpc_port: u16,
    pub http_port: u16,
    pub version: Option<String>,
    pub error: Option<String>,
}

/// Health check response from supervisor
#[derive(Debug, serde::Deserialize)]
#[allow(dead_code)]
struct HealthResponse {
    status: String,
    version: Option<String>,
    _components: Option<Vec<ComponentStatus>>,
}

#[derive(Debug, serde::Deserialize)]
#[allow(dead_code)]
struct ComponentStatus {
    _name: String,
    _status: String,
    #[serde(rename = "message")]
    _message: Option<String>,
}

/// Result of a daemon operation
#[derive(Debug, Clone, serde::Serialize)]
pub struct DaemonOperationResult {
    pub success: bool,
    pub message: String,
}

// Helper to create a const mutex
const fn const_mutex<T>(t: T) -> Mutex<T> {
    Mutex::const_new(t)
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
        
        // Check if the executable name exactly matches
        if exe_name == expected_name {
            return true;
        }
        
        // Also check if it's in a binaries folder and contains supervisor
        let exe_str = exe.to_string_lossy().to_lowercase();
        if exe_str.contains("binaries") && exe_str.contains("supervisor") {
            return true;
        }
    }
    
    // Check command line for more accuracy
    let cmd = process.cmd().join(" ");
    if cmd.contains("supervisor") && !cmd.contains("agentos-gui") {
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

/// Check if a TCP port is open
async fn is_port_open(port: u16) -> bool {
    match tokio::net::TcpStream::connect(format!("127.0.0.1:{}", port)).await {
        Ok(_) => true,
        Err(_) => false,
    }
}

/// Perform a health check via HTTP API
async fn check_http_health() -> Result<(bool, Option<String>), String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

    match client
        .get(format!("http://127.0.0.1:{}/health", SUPERVISOR_HTTP_PORT))
        .send()
        .await
    {
        Ok(response) => {
            if response.status().is_success() {
                match response.json::<HealthResponse>().await {
                    Ok(health) => {
                        let healthy = health.status == "healthy";
                        Ok((healthy, health.version))
                    }
                    Err(_) => Ok((true, None)), // HTTP success but couldn't parse JSON
                }
            } else {
                Ok((false, None))
            }
        }
        Err(e) => Err(format!("Health check failed: {}", e)),
    }
}

/// Get the log directory path
fn get_log_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("AgentOS")
        .join("logs")
}

/// Ensure log directory exists
fn ensure_log_dir() -> Result<PathBuf, String> {
    let log_dir = get_log_dir();
    std::fs::create_dir_all(&log_dir)
        .map_err(|e| format!("Failed to create log directory: {}", e))?;
    Ok(log_dir)
}

/// Stream stdout/stderr from a child process to log files
async fn stream_process_logs(
    stdout: tokio::process::ChildStdout,
    stderr: tokio::process::ChildStderr,
    log_dir: &PathBuf,
) -> Result<(), String> {
    let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
    let stdout_path = log_dir.join(format!("supervisor_{}_stdout.log", timestamp));
    let stderr_path = log_dir.join(format!("supervisor_{}_stderr.log", timestamp));

    let stdout_file = File::create(&stdout_path)
        .await
        .map_err(|e| format!("Failed to create stdout log file: {}", e))?;
    let stderr_file = File::create(&stderr_path)
        .await
        .map_err(|e| format!("Failed to create stderr log file: {}", e))?;

    // Spawn stdout reader task
    let stdout_path_str = stdout_path.to_string_lossy().to_string();
    tokio::spawn(async move {
        let mut reader = BufReader::new(stdout).lines();
        let mut file = stdout_file;
        
        while let Ok(Some(line)) = reader.next_line().await {
            if file.write_all(format!("{}\n", line).as_bytes()).await.is_err() {
                break;
            }
            if file.flush().await.is_err() {
                break;
            }
        }
        log::debug!("Stdout logging ended for: {}", stdout_path_str);
    });

    // Spawn stderr reader task
    let stderr_path_str = stderr_path.to_string_lossy().to_string();
    tokio::spawn(async move {
        let mut reader = BufReader::new(stderr).lines();
        let mut file = stderr_file;
        
        while let Ok(Some(line)) = reader.next_line().await {
            if file.write_all(format!("{}\n", line).as_bytes()).await.is_err() {
                break;
            }
            if file.flush().await.is_err() {
                break;
            }
        }
        log::debug!("Stderr logging ended for: {}", stderr_path_str);
    });

    Ok(())
}

/// Get daemon status
#[tauri::command]
pub async fn get_daemon_status() -> Result<DaemonStatus, String> {
    let process_info = find_supervisor_process();
    let grpc_reachable = is_port_open(SUPERVISOR_GRPC_PORT).await;
    let http_reachable = is_port_open(SUPERVISOR_HTTP_PORT).await;

    // If ports are reachable, perform HTTP health check for more detail
    let (healthy, version) = if http_reachable {
        match check_http_health().await {
            Ok((h, v)) => (h, v),
            Err(_) => (false, None),
        }
    } else {
        (false, None)
    };

    let running = process_info.is_some() && (grpc_reachable || http_reachable) && healthy;

    match process_info {
        Some((pid, uptime)) => Ok(DaemonStatus {
            running,
            pid: Some(pid),
            uptime_secs: Some(uptime),
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
            version,
            error: if running { None } else { Some("Supervisor not healthy".to_string()) },
        }),
        None => Ok(DaemonStatus {
            running: false,
            pid: None,
            uptime_secs: None,
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
            version: None,
            error: None,
        }),
    }
}

/// Start the supervisor daemon
#[tauri::command]
pub async fn start_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    // Check if already running
    let status = get_daemon_status().await?;
    if status.running {
        return Ok(status);
    }

    // Determine supervisor binary path
    let supervisor_bin = resolve_supervisor_binary(&app_handle)?;
    
    // Ensure log directory exists
    let log_dir = ensure_log_dir()?;

    // Spawn the supervisor process
    let mut child = Command::new(&supervisor_bin)
        .env("AGENTOS_RUNTIME_MODE", "grpc")
        .env("AGENTOS_DATA_DIR", get_data_dir().to_string_lossy().as_ref())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start supervisor '{}': {}", supervisor_bin.display(), e))?;

    let pid = child.id().ok_or_else(|| "Failed to get child PID".to_string())?;

    // Start log streaming if we have pipes
    if let (Some(stdout), Some(stderr)) = (child.stdout.take(), child.stderr.take()) {
        stream_process_logs(stdout, stderr, &log_dir).await?;
    }

    // Store child handle
    {
        let mut guard = DAEMON_PROCESS.lock().await;
        *guard = Some(child);
    }

    // Wait for supervisor to become healthy
    let health_check_result = timeout(
        Duration::from_secs(HEALTH_CHECK_TIMEOUT_SECS),
        wait_for_healthy(),
    )
    .await;

    match health_check_result {
        Ok(Ok((healthy, version))) => {
            if healthy {
                Ok(DaemonStatus {
                    running: true,
                    pid: Some(pid),
                    uptime_secs: Some(0),
                    grpc_port: SUPERVISOR_GRPC_PORT,
                    http_port: SUPERVISOR_HTTP_PORT,
                    version,
                    error: None,
                })
            } else {
                Err("Supervisor process started but is not healthy".to_string())
            }
        }
        Ok(Err(e)) => Err(format!("Health check error: {}", e)),
        Err(_) => {
            // Timeout - supervisor didn't become healthy
            // Try to kill the process
            let _ = kill_daemon_process().await;
            Err(format!(
                "Supervisor process started but did not become healthy within {} seconds",
                HEALTH_CHECK_TIMEOUT_SECS
            ))
        }
    }
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
    
    // Try without extension for non-Windows
    #[cfg(not(target_os = "windows"))]
    {
        let bundled_path_no_ext = app_handle
            .path_resolver()
            .resolve_resource("binaries/supervisor");
        if let Some(path) = bundled_path_no_ext {
            if path.exists() {
                return Ok(path);
            }
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
    
    // Try supervisor directory (development mode)
    let dev_path = PathBuf::from("supervisor").join(binary_name);
    if dev_path.exists() {
        return Ok(dev_path);
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

/// Wait for the supervisor to become healthy
async fn wait_for_healthy() -> Result<(bool, Option<String>), String> {
    loop {
        // Check both ports
        let grpc_open = is_port_open(SUPERVISOR_GRPC_PORT).await;
        let http_open = is_port_open(SUPERVISOR_HTTP_PORT).await;
        
        if grpc_open || http_open {
            // Ports are open, do a proper health check
            match check_http_health().await {
                Ok(result) => return Ok(result),
                Err(_) => {
                    // Health check failed but ports are open, might be starting up
                    sleep(Duration::from_millis(HEALTH_CHECK_INTERVAL_MS)).await;
                }
            }
        } else {
            sleep(Duration::from_millis(HEALTH_CHECK_INTERVAL_MS)).await;
        }
    }
}

/// Stop the supervisor daemon
#[tauri::command]
pub async fn stop_daemon() -> Result<DaemonStatus, String> {
    let status = get_daemon_status().await?;
    
    if !status.running {
        return Ok(DaemonStatus {
            running: false,
            pid: None,
            uptime_secs: None,
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
            version: None,
            error: None,
        });
    }

    // Try graceful shutdown strategies in order:
    // 1. HTTP POST to shutdown endpoint (if exists)
    // 2. Process termination via stored handle
    // 3. Process kill by PID

    // Strategy 1: Try HTTP shutdown endpoint
    let shutdown_success = try_http_shutdown().await;

    // Strategy 2: Try graceful process termination
    if !shutdown_success {
        try_graceful_termination().await;
    }

    // Strategy 3: Force kill
    if !shutdown_success {
        let _ = kill_daemon_process().await;
    }

    // Wait a moment for process to exit
    sleep(Duration::from_secs(2)).await;

    // Verify process is stopped
    let final_status = get_daemon_status().await?;
    
    if final_status.running {
        return Err("Failed to stop supervisor daemon. The process may require manual termination.".to_string());
    }

    Ok(DaemonStatus {
        running: false,
        pid: None,
        uptime_secs: None,
        grpc_port: SUPERVISOR_GRPC_PORT,
        http_port: SUPERVISOR_HTTP_PORT,
        version: None,
        error: None,
    })
}

/// Try to shut down via HTTP endpoint
async fn try_http_shutdown() -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };

    // Try shutdown endpoint
    match client
        .post(format!("http://127.0.0.1:{}/api/v1/shutdown", SUPERVISOR_HTTP_PORT))
        .send()
        .await
    {
        Ok(_) => true,
        Err(_) => {
            // Shutdown endpoint may not exist, that's okay
            false
        }
    }
}

/// Try graceful process termination
async fn try_graceful_termination() {
    #[cfg(unix)]
    {
        let mut guard = DAEMON_PROCESS.lock().await;
        if let Some(ref mut child) = *guard {
            // On Unix, try SIGTERM first
            unsafe {
                libc::kill(child.id().unwrap_or(0) as i32, libc::SIGTERM);
            }
            
            // Wait a moment for graceful shutdown
            sleep(Duration::from_secs(3)).await;
            
            // Check if still running
            match child.try_wait() {
                Ok(Some(_)) => return, // Process exited
                Ok(None) => return,   // Still running, will be killed later
                Err(_) => return,
            }
        }
    }
    
    #[cfg(windows)]
    {
        // On Windows, there's no direct graceful termination
        // Just wait a bit and let the caller try kill
        sleep(Duration::from_secs(2)).await;
    }
}

/// Kill the daemon process
async fn kill_daemon_process() -> Result<(), String> {
    // First try via stored handle
    {
        let mut guard = DAEMON_PROCESS.lock().await;
    if let Some(ref mut child) = *guard {
            let _ = child.kill().await;
            *guard = None;
            return Ok(());
        }
    }
    
    // Fallback: kill by PID
    if let Some((pid, _)) = find_supervisor_process() {
        let mut system = System::new_with_specifics(
            RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
        );
        system.refresh_processes();
        
        if let Some(process) = system.process(sysinfo::Pid::from_u32(pid)) {
            if process.kill() {
                return Ok(());
            } else {
                return Err(format!("Failed to kill process {}", pid));
            }
        }
    }
    
    Err("No supervisor process found to kill".to_string())
}

/// Restart the supervisor daemon
#[tauri::command]
pub async fn restart_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    // First stop the daemon (ignore errors as it may not be running)
    let _ = stop_daemon().await;
    
    // Wait a moment to ensure clean shutdown
    sleep(Duration::from_secs(2)).await;
    
    // Then start it again
    match start_daemon(app_handle).await {
        Ok(status) => Ok(status),
        Err(e) => {
            // If start failed, try to provide helpful error message
            Err(format!("Failed to restart supervisor: {}. The supervisor may be in an inconsistent state.", e))
        }
    }
}

/// Clean up the daemon process on app exit
pub async fn cleanup_daemon() -> Result<(), String> {
    let status = get_daemon_status().await?;
    
    if status.running {
        log::info!("Cleaning up supervisor daemon on app exit...");
        
        // Try graceful shutdown first
        match timeout(Duration::from_secs(10), stop_daemon()).await {
            Ok(Ok(_)) => {
                log::info!("Supervisor daemon stopped gracefully");
                Ok(())
            }
            Ok(Err(e)) => {
                log::warn!("Failed to stop supervisor gracefully: {}", e);
                // Force kill as last resort
                let _ = kill_daemon_process().await;
                Ok(())
            }
            Err(_) => {
                log::warn!("Supervisor shutdown timed out, forcing kill");
                let _ = kill_daemon_process().await;
                Ok(())
            }
        }
    } else {
        Ok(())
    }
}

/// Check if the daemon is installed and available
#[tauri::command]
pub async fn check_daemon_installation(app_handle: AppHandle) -> Result<DaemonOperationResult, String> {
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
