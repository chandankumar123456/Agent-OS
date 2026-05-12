use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use sysinfo::{ProcessRefreshKind, RefreshKind, System};
use tauri::AppHandle;

static DAEMON_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

const SUPERVISOR_GRPC_PORT: u16 = 50051;
const SUPERVISOR_HTTP_PORT: u16 = 8080;

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct DaemonStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub uptime_secs: Option<u64>,
    pub grpc_port: u16,
    pub http_port: u16,
}

fn find_supervisor_process() -> Option<(u32, u64)> {
    let mut system = System::new_with_specifics(
        RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
    );
    system.refresh_processes();

    for (pid, process) in system.processes() {
        if let Some(exe) = process.exe() {
            let exe_str = exe.to_string_lossy().to_lowercase();
            if exe_str.contains("supervisor") || exe_str.contains("agentos") {
                return Some((pid.as_u32(), process.run_time()));
            }
        }
    }
    None
}

fn is_port_open(port: u16) -> bool {
    std::net::TcpStream::connect(format!("127.0.0.1:{}", port)).is_ok()
}

#[tauri::command]
pub async fn get_daemon_status() -> Result<DaemonStatus, String> {
    let grpc_reachable = is_port_open(SUPERVISOR_GRPC_PORT);
    let http_reachable = is_port_open(SUPERVISOR_HTTP_PORT);

    if let Some((pid, uptime)) = find_supervisor_process() {
        Ok(DaemonStatus {
            running: grpc_reachable || http_reachable,
            pid: Some(pid),
            uptime_secs: Some(uptime),
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
        })
    } else {
        Ok(DaemonStatus {
            running: false,
            pid: None,
            uptime_secs: None,
            grpc_port: SUPERVISOR_GRPC_PORT,
            http_port: SUPERVISOR_HTTP_PORT,
        })
    }
}

#[tauri::command]
pub async fn start_daemon(app_handle: AppHandle) -> Result<DaemonStatus, String> {
    let status = get_daemon_status().await?;
    if status.running {
        return Ok(status);
    }

    // Determine supervisor binary path
    // Try bundled resource first, then PATH
    let supervisor_bin = app_handle
        .path_resolver()
        .resolve_resource("binaries/supervisor")
        .or_else(|| {
            #[cfg(target_os = "windows")]
            {
                app_handle
                    .path_resolver()
                    .resolve_resource("binaries/supervisor.exe")
            }
            #[cfg(not(target_os = "windows"))]
            {
                None
            }
        })
        .unwrap_or_else(|| std::path::PathBuf::from("supervisor"));

    let child = Command::new(&supervisor_bin)
        .env("AGENTOS_RUNTIME_MODE", "grpc")
        .env("DATABASE_URL", "sqlite://~/.agentos/agentos.db")
        .env("REDIS_URL", "")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start supervisor: {}", e))?;

    let pid = child.id();

    // Store child handle
    if let Ok(mut guard) = DAEMON_PROCESS.lock() {
        *guard = Some(child);
    }

    // Wait up to 10 seconds for ports to become reachable
    for _ in 0..100 {
        if is_port_open(SUPERVISOR_HTTP_PORT) || is_port_open(SUPERVISOR_GRPC_PORT) {
            return Ok(DaemonStatus {
                running: true,
                pid: Some(pid),
                uptime_secs: Some(0),
                grpc_port: SUPERVISOR_GRPC_PORT,
                http_port: SUPERVISOR_HTTP_PORT,
            });
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    Err("Supervisor process started but did not become reachable within 10 seconds".to_string())
}

#[tauri::command]
pub async fn stop_daemon() -> Result<DaemonStatus, String> {
    let status = get_daemon_status().await?;
    if !status.running {
        return Ok(status);
    }

    // Try graceful shutdown via HTTP first
    let client = reqwest::Client::new();
    let _ = client
        .post(format!("http://127.0.0.1:{}/api/v1/shutdown", SUPERVISOR_HTTP_PORT))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await;

    // Wait a moment for graceful shutdown
    std::thread::sleep(std::time::Duration::from_secs(2));

    // Check if still running
    let status_after = get_daemon_status().await?;
    if status_after.running {
        // Force kill if still running
        if let Some(pid) = status_after.pid {
            let mut system = System::new_with_specifics(
                RefreshKind::new().with_processes(ProcessRefreshKind::everything()),
            );
            system.refresh_processes();
            if let Some(process) = system.process(sysinfo::Pid::from_u32(pid)) {
                process.kill();
            }
        }
    }

    // Clear stored child handle
    if let Ok(mut guard) = DAEMON_PROCESS.lock() {
        *guard = None;
    }

    Ok(DaemonStatus {
        running: false,
        pid: None,
        uptime_secs: None,
        grpc_port: SUPERVISOR_GRPC_PORT,
        http_port: SUPERVISOR_HTTP_PORT,
    })
}
